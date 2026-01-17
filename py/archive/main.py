import time
import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry
import pymysql  # 需要先 pip install PyMySQL
import redis  # 需要先 pip install redis
import logging
from datetime import datetime, timedelta
import yaml
import os

# --- 日志配置 ---
# 配置日志格式，同时输出到终端和可选的日志文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

# --- 加载配置 ---
def load_config():
    """
    从配置文件加载配置，如果配置文件不存在则使用默认值
    """
    config_path = 'config.yaml'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
        # 默认配置
        config = {
            "archive_config": {
                "increment_value": 10000,
                "default_min_id_value": 10000,
                "total_iterations": 1000
            },
            "database": {
                "host": "x",
                "port": 30001,
                "user": "x",
                "password": "x",
                "database": "x",
                "charset": "utf8mb4"
            },
            "redis": {
                "host": "x",
                "port": 36379,
                "password": "xxx",
                "db": 0,
                "decode_responses": True
            },
            "api": {
                "url": "https://xxx"
            },
            "lock": {
                "key": "x",
                "wait_seconds": 30
            },
            "thread_pool": {
                "max_workers": 5
            },
            "retry_policy": {
                "total": 3,
                "backoff_factor": 1,
                "status_forcelist": [429, 500, 502, 503, 504]
            },
            "connection_pool": {
                "pool_connections": 10,
                "pool_maxsize": 20
            }
        }
    
    return config

config = load_config()

# 从配置文件加载配置值
ARCHIVE_INCREMENT_VALUE = config['archive_config']['increment_value']
DEFAULT_MIN_ID_VALUE = config['archive_config']['default_min_id_value']
total_iterations = config['archive_config']['total_iterations']

# 请务必修改以下数据库连接参数为您实际的数据库信息
DB_CONFIG = {
    'host': config['database']['host'],
    'port': config['database']['port'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'database': config['database']['database'],
    'charset': config['database']['charset']
}

# 请务必修改以下 Redis 连接参数为您实际的 Redis 信息
REDIS_CONFIG = {
    'host': config['redis']['host'],
    'port': config['redis']['port'],
    'password': config['redis']['password'],
    'db': config['redis']['db'],
    'decode_responses': config['redis']['decode_responses']
}

API_URL = config['api']['url']
LOCK_KEY = config['lock']['key']  # Redis 中的锁键名
WAIT_SECONDS_FOR_LOCK_CHECK = config['lock']['wait_seconds']  # 检查 Redis 锁时，每次轮询的间隔时间

# 创建全局会话对象，启用连接池和长连接
session = requests.Session()

# 配置重试策略
retry_strategy = Retry(
    total=config['retry_policy']['total'],
    backoff_factor=config['retry_policy']['backoff_factor'],
    status_forcelist=config['retry_policy']['status_forcelist'],
)

# 配置适配器，应用重试策略
adapter = HTTPAdapter(
    pool_connections=config['connection_pool']['pool_connections'],  # 连接池的连接数
    pool_maxsize=config['connection_pool']['pool_maxsize'],      # 最大连接数
    max_retries=retry_strategy
)

# 为HTTP和HTTPS请求挂载适配器
session.mount("http://", adapter)
session.mount("https://", adapter)

# 线程池大小配置
MAX_WORKERS = config['thread_pool']['max_workers']  # 最大并发线程数

# --- 配置加载完成 ---


def check_long_connection_support(url):
    """
    检查指定URL是否支持长连接
    """
    try:
        # 发送一个HEAD请求来检查Connection头部
        response = session.head(url, timeout=10)
        
        # 检查响应头部中是否支持长连接
        connection_header = response.headers.get('Connection', '').lower()
        keep_alive_header = response.headers.get('Keep-Alive', '')
        
        # HTTP/1.1 默认支持长连接，除非明确指定 Connection: close
        is_http11 = response.version == 11 if hasattr(response, 'version') else True
        is_close = connection_header == 'close'
        
        supports_keepalive = (is_http11 and not is_close) or connection_header == 'keep-alive'
        
        logger.info(f"  🔍 长连接检查结果: 支持长连接={supports_keepalive}, Connection头部='{connection_header}', Keep-Alive='{keep_alive_header}'")
        
        return supports_keepalive
    except Exception as e:
        logger.error(f"  ❌ 检查长连接支持时发生错误: {e}")
        return False

def initialize_and_update():
    """
    初始化函数：根据表名和ttx_archive_rule_term中的field、operator、value条件，查询出MIN(id)并更新到归档规则中
    同时考虑时间条件：表.created < ttx_archive_rule_header.archiveDaysBefore
    """
    db_connection = None
    redis_client = None

    try:
        # 连接数据库
        logger.info("正在连接数据库...")
        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()

        # 连接 Redis
        logger.info("正在连接 Redis...")
        redis_client = redis.Redis(**REDIS_CONFIG)
        # 尝试执行一个简单的 Redis 命令来测试连接
        redis_client.ping()
        logger.info("Redis 连接成功。")

        # 查询所有 autoArchive=1 的表头信息，包括归档天数设置
        logger.info("正在查询 ttx_archive_rule_header 表中 autoArchive=1 的记录...")
        query_sql = "SELECT id, tableName, archiveDaysBefore FROM ttx_archive_rule_header WHERE autoArchive=1"
        db_cursor.execute(query_sql)
        table_records = db_cursor.fetchall()

        if not table_records:
            logger.warning("未找到 autoArchive=1 的表记录，程序退出。")
            return

        logger.info(f"共查询到 {len(table_records)} 个需要归档的表:")
        for record in table_records:
            logger.info(f"  - ID: {record[0]}, TableName: {record[1]}, ArchiveDaysBefore: {record[2]}")

        # 对每个表进行初始化操作
        for header_id, table_name, archive_days_before in table_records:
            logger.info(f"\n--- 开始处理表 {table_name} (ID: {header_id}, 归档天数: {archive_days_before}) ---")

            # 查询该表头对应的规则条件
            rule_query = "SELECT field, operator, value FROM ttx_archive_rule_term WHERE headerId=%s;"
            db_cursor.execute(rule_query, (header_id,))
            rules = db_cursor.fetchall()

            # 计算归档日期阈值，并将时分秒调整为 00:00:00
            if archive_days_before is not None and archive_days_before > 0:
                archive_date_raw = datetime.now() - timedelta(days=archive_days_before)
                # 获取日期部分，并组合为当天的 00:00:00
                archive_date_threshold = datetime.combine(archive_date_raw.date(), datetime.min.time())
                logger.info(f"    归档日期阈值: {archive_date_threshold.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                logger.info(f"    未设置归档天数，设置默认时间条件180天")
                archive_date_raw_default = datetime.now() - timedelta(days=180)
                # 获取日期部分，并组合为当天的 00:00:00
                archive_date_threshold = datetime.combine(archive_date_raw_default.date(), datetime.min.time())

            if not rules:
                logger.warning(
                    f"  表 {table_name} (ID: {header_id}) 没有找到任何规则条件，设置默认值{DEFAULT_MIN_ID_VALUE}")

                # 检查是否存在 id < X 的规则，如果没有则插入
                check_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                db_cursor.execute(check_sql, (header_id,))
                existing_result = db_cursor.fetchone()

                if existing_result:
                    # 如果已有规则，更新为默认值
                    update_sql = f"UPDATE ttx_archive_rule_term SET `value`={DEFAULT_MIN_ID_VALUE} WHERE headerId=%s AND field='id' AND operator='<';"
                    db_cursor.execute(update_sql, (header_id,))
                    affected_rows = db_cursor.rowcount
                    logger.info(f"    ✓ 更新了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")
                else:
                    # 如果没有规则，插入新的规则
                    insert_sql = """
                    INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                    VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'INIT_SYSTEM', 'INIT_SYSTEM');
                    """
                    db_cursor.execute(insert_sql, (header_id, DEFAULT_MIN_ID_VALUE))
                    affected_rows = db_cursor.rowcount
                    logger.info(f"    ✓ 插入了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")

                continue  # 继续处理下一个表

            # 构建动态WHERE条件，排除field='id'的规则
            where_conditions = []
            params = []

            for field, operator, value in rules:
                if field.lower() != 'id':
                    # 添加到WHERE条件
                    where_conditions.append(f"`{field}` {operator} %s")
                    # 确保参数类型正确，移除可能存在的额外引号
                    if isinstance(value, str):
                        # 移除可能存在的首尾引号
                        cleaned_value = value.strip().strip("'").strip('"')
                        params.append(cleaned_value)
                    else:
                        params.append(value)

            # 添加时间条件：created < archive_date_threshold
            if archive_date_threshold is not None:
                where_conditions.append("`created` < %s")
                params.append(archive_date_threshold.strftime('%Y-%m-%d %H:%M:%S'))

            if not where_conditions:
                # 如果没有其他条件，则直接查询最小ID
                dynamic_query = f"SELECT MIN(id) as min_id FROM `{table_name}`"
                params = []
            else:
                # 构建带有WHERE条件的查询
                where_clause = " AND ".join(where_conditions)
                dynamic_query = f"SELECT MIN(id) as min_id FROM `{table_name}` WHERE {where_clause}"

            try:
                # 执行前先进行调试查询，确保参数传递正确
                logger.info(f"  执行查询: {dynamic_query}  参数: {params}")

                # 尝试手动构建SQL查询用于调试（仅用于调试目的，不执行）
                debug_query = dynamic_query
                for param in params:
                    if isinstance(param, str):
                        debug_query = debug_query.replace('%s', f"'{param}'", 1)  # PyMySQL会自动处理引号
                    else:
                        debug_query = debug_query.replace('%s', str(param), 1)
                logger.info(f"  调试用的实际查询: {debug_query}")

                db_cursor.execute(dynamic_query, params)
                result = db_cursor.fetchone()

                # 添加结果调试信息
                logger.info(f"  查询结果: {result}")
                if result:
                    logger.info(f"  结果长度: {len(result)}, 第一个元素: {result[0] if len(result) > 0 else 'N/A'}")

                if result and result[0] is not None:
                    min_id = int(result[0])
                    logger.info(f"  表 {table_name} 中满足条件的最小ID为: {min_id}")

                    # 更新或插入 id < X 的规则
                    # 检查 ttx_archive_rule_term 中是否已有 id < X 的规则
                    check_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                    db_cursor.execute(check_sql, (header_id,))
                    existing_result = db_cursor.fetchone()

                    if existing_result:
                        # 如果已有规则，更新为最小ID
                        update_sql = "UPDATE ttx_archive_rule_term SET `value`=%s WHERE headerId=%s AND field='id' AND operator='<';"
                        db_cursor.execute(update_sql, (min_id, header_id))
                        affected_rows = db_cursor.rowcount
                        logger.info(f"    ✓ 更新了 {affected_rows} 条记录，value 设置为最小ID {min_id}")
                    else:
                        # 如果没有规则，插入新的规则
                        insert_sql = """
                        INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                        VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'INIT_SYSTEM', 'INIT_SYSTEM');
                        """
                        db_cursor.execute(insert_sql, (header_id, min_id))
                        affected_rows = db_cursor.rowcount
                        logger.info(f"    ✓ 插入了 {affected_rows} 条记录，value 设置为最小ID {min_id}")
                else:
                    # 在这种情况下，我们需要先检查是否有满足条件的记录存在
                    # 重新构建查询来检查是否存在满足条件的记录
                    if not where_conditions:
                        count_query = f"SELECT COUNT(*) as count FROM `{table_name}`"
                        count_params = []
                    else:
                        count_query = f"SELECT COUNT(*) as count FROM `{table_name}` WHERE {where_clause}"
                        count_params = params

                    logger.info(f"  检查是否存在满足条件的记录: {count_query}  参数: {count_params}")
                    db_cursor.execute(count_query, count_params)
                    count_result = db_cursor.fetchone()

                    if count_result and count_result[0] > 0:
                        logger.warning(
                            f"  检测到存在满足条件的记录({count_result[0]}条)，但MIN(id)为NULL，可能存在空值或特殊数据类型")

                        # 添加额外的调试查询来确认数据确实存在
                        debug_where_clause = " AND ".join(where_conditions)
                        debug_query = f"SELECT id, created FROM `{table_name}` WHERE {debug_where_clause} LIMIT 5"
                        logger.info(f"  调试查询: {debug_query}  参数: {params}")
                        # 重新执行调试查询，确保参数处理正确
                        db_cursor.execute(debug_query, params)
                        debug_results = db_cursor.fetchall()
                        logger.info(f"  调试结果: {debug_results}")

                        # 检查是否是数据类型问题
                        id_values_query = f"SELECT id FROM `{table_name}` WHERE {where_clause} AND id IS NOT NULL ORDER BY id ASC LIMIT 10"
                        logger.info(f"  ID值检查查询: {id_values_query}  参数: {params}")
                        db_cursor.execute(id_values_query, params)
                        id_results = db_cursor.fetchall()
                        logger.info(f"  ID值结果: {id_results}")

                        # 尝试查询所有满足条件的ID并找最小值
                        all_ids_query = f"SELECT id FROM `{table_name}`"
                        if where_conditions:
                            all_ids_query += f" WHERE {where_clause}"
                        all_ids_query += " AND id IS NOT NULL ORDER BY id ASC LIMIT 1"

                        logger.info(f"  尝试查询非空ID的最小值: {all_ids_query}  参数: {params}")
                        db_cursor.execute(all_ids_query, params)
                        all_ids_result = db_cursor.fetchone()

                        if all_ids_result and all_ids_result[0] is not None:
                            min_id = int(all_ids_result[0])
                            logger.info(f"  成功找到非空最小ID: {min_id}")

                            # 更新或插入 id < X 的规则
                            check_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                            db_cursor.execute(check_sql, (header_id,))
                            existing_result = db_cursor.fetchone()

                            if existing_result:
                                update_sql = "UPDATE ttx_archive_rule_term SET `value`=%s WHERE headerId=%s AND field='id' AND operator='<';"
                                db_cursor.execute(update_sql, (min_id, header_id))
                                affected_rows = db_cursor.rowcount
                                logger.info(f"    ✓ 更新了 {affected_rows} 条记录，value 设置为最小ID {min_id}")
                            else:
                                insert_sql = """
                                INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                                VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'INIT_SYSTEM', 'INIT_SYSTEM');
                                """
                                db_cursor.execute(insert_sql, (header_id, min_id))
                                affected_rows = db_cursor.rowcount
                                logger.info(f"    ✓ 插入了 {affected_rows} 条记录，value 设置为最小ID {min_id}")
                        else:
                            logger.warning(f"  仍然无法找到有效的ID值，设置默认值{DEFAULT_MIN_ID_VALUE}")

                            # 检查 ttx_archive_rule_term 中是否已有 id < X 的规则
                            check_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                            db_cursor.execute(check_sql, (header_id,))
                            existing_result = db_cursor.fetchone()

                            if existing_result:
                                # 如果已有规则，更新为默认值
                                update_sql = f"UPDATE ttx_archive_rule_term SET `value`={DEFAULT_MIN_ID_VALUE} WHERE headerId=%s AND field='id' AND operator='<';"
                                db_cursor.execute(update_sql, (header_id,))
                                affected_rows = db_cursor.rowcount
                                logger.info(
                                    f"    ✓ 更新了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")
                            else:
                                # 如果没有规则，插入新的规则
                                insert_sql = """
                                INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                                VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'INIT_SYSTEM', 'INIT_SYSTEM');
                                """
                                db_cursor.execute(insert_sql, (header_id, DEFAULT_MIN_ID_VALUE))
                                affected_rows = db_cursor.rowcount
                                logger.info(
                                    f"    ✓ 插入了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")
                    else:
                        logger.info(
                            f"  确认表 {table_name} 中确实没有满足条件的记录({count_result[0]}条)，设置默认值{DEFAULT_MIN_ID_VALUE}")

                        # 检查 ttx_archive_rule_term 中是否已有 id < X 的规则
                        check_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                        db_cursor.execute(check_sql, (header_id,))
                        existing_result = db_cursor.fetchone()

                        if existing_result:
                            # 如果已有规则，更新为默认值
                            update_sql = f"UPDATE ttx_archive_rule_term SET `value`={DEFAULT_MIN_ID_VALUE} WHERE headerId=%s AND field='id' AND operator='<';"
                            db_cursor.execute(update_sql, (header_id,))
                            affected_rows = db_cursor.rowcount
                            logger.info(
                                f"    ✓ 更新了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")
                        else:
                            # 如果没有规则，插入新的规则
                            insert_sql = """
                            INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                            VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'INIT_SYSTEM', 'INIT_SYSTEM');
                            """
                            db_cursor.execute(insert_sql, (header_id, DEFAULT_MIN_ID_VALUE))
                            affected_rows = db_cursor.rowcount
                            logger.info(
                                f"    ✓ 插入了 {affected_rows} 条记录，value 设置为默认值 {DEFAULT_MIN_ID_VALUE}")

            except pymysql.Error as e:
                logger.error(f"  查询表 {table_name} 时发生错误: {e}")
                continue  # 继续处理下一个表

        # 提交事务以确保更改生效
        db_connection.commit()
        logger.info(f"  ✓ 数据库事务提交成功")

        logger.info(f"\n{'=' * 70}")
        logger.info(f"📊 初始化任务完成")
        logger.info(f"{'=' * 70}")
        logger.info(f"🎉 所有表的归档规则已根据其数据表中的条件查询结果设置了最小ID")
        logger.info(f"{'=' * 70}")

    except pymysql.Error as e:
        logger.error(f"数据库操作错误: {e}")
    except redis.ConnectionError as e:
        logger.error(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.error(f"脚本执行过程中发生未知错误: {e}")
        logger.exception("详细错误信息:")  # 记录完整的堆栈跟踪
    finally:
        # 关闭数据库连接
        if db_connection:
            try:
                db_cursor.close()
                db_connection.close()
                logger.info("✓ 数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接时发生错误: {e}")
        # 关闭 Redis 连接
        if redis_client:
            try:
                logger.info("✓ Redis 连接已处理")
            except Exception as e:
                logger.error(f"处理 Redis 连接时发生错误: {e}")


def update_and_request():
    """
    主循环函数：查询表头信息，更新归档规则值，请求API、并等待归档任务完成
    """
    db_connection = None
    redis_client = None
    execution_times = []  # 存储每次归档执行的时间

    try:
        # 连接数据库
        logger.info("正在连接数据库...")
        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()

        # 连接 Redis
        logger.info("正在连接 Redis...")
        redis_client = redis.Redis(**REDIS_CONFIG)
        # 尝试执行一个简单的 Redis 命令来测试连接
        redis_client.ping()
        logger.info("Redis 连接成功。")

        # 查询所有 autoArchive=1 的表头信息，包括归档天数设置
        logger.info("正在查询 ttx_archive_rule_header 表中 autoArchive=1 的记录...")
        query_sql = "SELECT id, tableName, archiveDaysBefore FROM ttx_archive_rule_header WHERE autoArchive=1"
        db_cursor.execute(query_sql)
        table_records = db_cursor.fetchall()

        if not table_records:
            logger.warning("未找到 autoArchive=1 的表记录，程序退出。")
            return

        logger.info(f"共查询到 {len(table_records)} 个需要归档的表:")
        for record in table_records:
            logger.info(f"  - ID: {record[0]}, TableName: {record[1]}, ArchiveDaysBefore: {record[2]}")

        current_iteration = 0

        for iteration in range(total_iterations):
            current_iteration += 1
            progress_percentage = (current_iteration / total_iterations) * 100

            # 1. 检查 Redis 锁，等待归档任务完成
            logger.info(f"[{progress_percentage:.1f}%] 检查 Redis 锁 {LOCK_KEY} 是否存在，以确定归档任务是否仍在执行...")
            lock_check_start_time = time.time()
            while True:
                if redis_client.exists(LOCK_KEY):
                    elapsed_time = int(time.time() - lock_check_start_time)
                    logger.info(
                        f"    锁 {LOCK_KEY} 存在，归档任务仍在执行中。已等待 {elapsed_time}s，继续等待 {WAIT_SECONDS_FOR_LOCK_CHECK} 秒后重试...")
                    time.sleep(WAIT_SECONDS_FOR_LOCK_CHECK)
                else:
                    elapsed_time = int(time.time() - lock_check_start_time)
                    logger.info(f"    锁 {LOCK_KEY} 不存在，归档任务已结束。等待了 {elapsed_time} 秒。")
                    break

            logger.info(f"\n{'=' * 60}")
            logger.info(
                f"处理进度: [{current_iteration}/{total_iterations}] | 当前迭代: {iteration} | 完成率: {progress_percentage:.1f}%")
            logger.info(f"{'=' * 60}")

            # 记录归档开始时间
            archive_start_time = time.time()
            logger.info(
                f"  🕐 归档任务开始时间: {datetime.fromtimestamp(archive_start_time).strftime('%Y-%m-%d %H:%M:%S')}")

            # 2. 查询当前所有表头ID对应的现有value值，并递增{ARCHIVE_INCREMENT_VALUE}
            for header_id, table_name, archive_days_before in table_records:
                # 先查询当前的value值
                select_sql = "SELECT value FROM ttx_archive_rule_term WHERE headerId=%s AND field='id' AND operator='<';"
                db_cursor.execute(select_sql, (header_id,))
                result = db_cursor.fetchone()

                if result:
                    current_value = int(result[0])
                    new_value = current_value + ARCHIVE_INCREMENT_VALUE
                    logger.info(f"  处理表 {table_name} (ID: {header_id}): 当前值 {current_value}, 更新为 {new_value}")

                    # 执行更新
                    update_sql = "UPDATE ttx_archive_rule_term SET `value`=%s WHERE headerId=%s AND field='id' AND operator='<';"
                    db_cursor.execute(update_sql, (new_value, header_id))
                    affected_rows = db_cursor.rowcount
                    logger.info(f"    ✓ 更新了 {affected_rows} 条记录，value 设置为 {new_value}")
                else:
                    # 如果没有找到匹配的规则，插入默认值{DEFAULT_MIN_ID_VALUE}
                    logger.info(
                        f"  警告: 表 {table_name} (ID: {header_id}) 没有找到 field='id' 且 operator='<' 的规则，插入默认值{DEFAULT_MIN_ID_VALUE}")

                    # 插入新的规则
                    insert_sql = """
                    INSERT INTO ttx_archive_rule_term (headerId, field, operator, value, created, lastUpdated, createdBy, lastUpdatedBy)
                    VALUES (%s, 'id', '<', %s, NOW(), NOW(), 'SYSTEM', 'SYSTEM')
                    ON DUPLICATE KEY UPDATE value = %s, lastUpdated = NOW(), lastUpdatedBy = 'SYSTEM';
                    """
                    db_cursor.execute(insert_sql, (header_id, DEFAULT_MIN_ID_VALUE, DEFAULT_MIN_ID_VALUE))
                    affected_rows = db_cursor.rowcount
                    logger.info(f"    ✓ 插入了 {affected_rows} 条记录，value 设置为 {DEFAULT_MIN_ID_VALUE}")

            # 提交事务以确保更改生效
            db_connection.commit()
            logger.info(f"  ✓ 数据库事务提交成功")

            # 3. 请求 API
            logger.info(f"  → 正在请求 API: {API_URL}")
            api_start_time = time.time()
            try:
                # 使用会话对象，支持长连接
                response = session.post(API_URL, timeout=30)
                api_end_time = time.time()
                api_duration = api_end_time - api_start_time
                logger.info(f"  ← API 请求完成，状态码: {response.status_code}，耗时: {api_duration:.2f}秒")

                # 根据您的 API 文档判断成功与否
                if response.status_code == 200:
                    logger.info(f"  ✓ API 请求成功")
                else:
                    logger.warning(f"  ⚠️  API 请求返回非200状态码: {response.status_code}")

                # 可选：记录响应内容（如果需要调试）
                # logger.debug(f"    响应内容: {response.text[:200]}...")  # 只记录前200字符

            except requests.exceptions.Timeout:
                logger.error(f"  ❌ API 请求超时 (30秒)")
            except requests.exceptions.ConnectionError:
                logger.error(f"  ❌ API 连接错误")
            except requests.exceptions.RequestException as e:
                logger.error(f"  ❌ API 请求发生错误: {e}")
                # 如果API出错，您可能希望暂停或退出，这里只是打印错误继续循环
                # raise # 取消注释这行可以让脚本在此处停止

            # 等待归档任务完成
            logger.info(f"  🔄 等待归档任务完成...")
            archive_wait_start = time.time()
            while True:
                if redis_client.exists(LOCK_KEY):
                    time.sleep(WAIT_SECONDS_FOR_LOCK_CHECK)
                else:
                    break
            archive_wait_duration = time.time() - archive_wait_start
            logger.info(f"  ✅ 归档任务已完成，等待耗时: {archive_wait_duration:.2f}秒")

            # 计算本次归档的总耗时
            archive_total_duration = time.time() - archive_start_time
            execution_times.append({
                'iteration': iteration,
                'duration': archive_total_duration,
                'start_time': datetime.fromtimestamp(archive_start_time),
                'end_time': datetime.fromtimestamp(time.time())
            })

            logger.info(f"  📊 本次归档总耗时: {archive_total_duration:.2f}秒 ({archive_total_duration / 60:.2f}分钟)")
            logger.info(
                f"  📅 归档时间段: {datetime.fromtimestamp(archive_start_time).strftime('%H:%M:%S')} -> {datetime.fromtimestamp(time.time()).strftime('%H:%M:%S')}")

        # 输出统计摘要
        logger.info(f"\n{'=' * 70}")
        logger.info(f"📊 归档任务执行统计摘要")
        logger.info(f"{'=' * 70}")

        if execution_times:
            total_duration = sum(item['duration'] for item in execution_times)
            avg_duration = total_duration / len(execution_times)
            max_duration = max(execution_times, key=lambda x: x['duration'])
            min_duration = min(execution_times, key=lambda x: x['duration'])

            logger.info(f"总执行次数: {len(execution_times)}")
            logger.info(f"总耗时: {total_duration:.2f}秒 ({total_duration / 60:.2f}分钟)")
            logger.info(f"平均耗时: {avg_duration:.2f}秒 ({avg_duration / 60:.2f}分钟)")
            logger.info(f"最长耗时: {max_duration['duration']:.2f}秒 (迭代: {max_duration['iteration']})")
            logger.info(f"最短耗时: {min_duration['duration']:.2f}秒 (迭代: {min_duration['iteration']})")

        logger.info(f"{'=' * 70}")
        logger.info(f"🎉 所有循环执行完毕！总计处理了 {total_iterations} 次迭代")
        logger.info(f"{'=' * 70}")

    except pymysql.Error as e:
        logger.error(f"数据库操作错误: {e}")
    except redis.ConnectionError as e:
        logger.error(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.error(f"脚本执行过程中发生未知错误: {e}")
        logger.exception("详细错误信息:")  # 记录完整的堆栈跟踪
    finally:
        # 关闭数据库连接
        if db_connection:
            try:
                db_cursor.close()
                db_connection.close()
                logger.info("✓ 数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接时发生错误: {e}")
        # 关闭 Redis 连接
        if redis_client:
            try:
                logger.info("✓ Redis 连接已处理")
            except Exception as e:
                logger.error(f"处理 Redis 连接时发生错误: {e}")


if __name__ == "__main__":
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("🚀 开始执行 WMS 归档任务管理脚本")
    logger.info("📋 脚本将先进行初始化，然后统计每次归档任务的执行时间")
    logger.info("=" * 70)

    # 检查API是否支持长连接
    logger.info("\n--- 检查API长连接支持情况 ---")
    is_long_connection_supported = check_long_connection_support(API_URL)
    if is_long_connection_supported:
        logger.info("✅ API 支持长连接，将使用连接池和会话复用优化性能")
    else:
        logger.warning("⚠️  API 可能不支持长连接，但仍将尝试使用连接池")

    # 先执行初始化
    logger.info("\n--- 开始执行初始化步骤 ---")
    initialize_and_update()
    logger.info("\n--- 初始化步骤完成，开始执行归档任务 ---\n")

    # 再执行归档任务
    update_and_request()

    end_time = time.time()
    duration = end_time - start_time
    logger.info("=" * 70)
    logger.info(f"🏁 脚本执行完成，总耗时: {duration:.2f} 秒 ({duration / 60:.2f} 分钟)")
    logger.info("=" * 70)
