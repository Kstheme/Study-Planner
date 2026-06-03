"""
PostgreSQL 数据库连接和基本功能测试

本测试文件用于验证 Study-Planner 项目与 PostgreSQL 数据库的连接和基本操作功能，
包括数据库连接、表创建、数据插入、查询、更新和删除等基本 CRUD 操作。
"""

import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

import pytest
import psycopg
from psycopg import sql


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://edudiag:123456@localhost:5433/study_planner")


def get_connection_params():
    """
    从环境变量解析数据库连接参数。

    读取 DATABASE_URL 环境变量并解析为 psycopg 所需的连接参数字典，
    支持 SQLAlchemy 格式的连接字符串。

    Returns:
        dict: 包含 host、port、dbname、user、password 等连接参数的字典。

    Raises:
        ValueError: 当 DATABASE_URL 格式不正确时抛出异常。
    """
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://edudiag:123456@localhost:5433/study_planner")
    
    if database_url.startswith("postgresql+psycopg://"):
        database_url = database_url.replace("postgresql+psycopg://", "postgresql://")
    
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "")
    
    user_password, host_port_db = database_url.split("@")
    user, password = user_password.split(":")
    host_port, dbname = host_port_db.split("/")
    host, port = host_port.split(":")
    
    params = {
        "host": host,
        "port": int(port),
        "dbname": dbname,
        "user": user,
        "password": password,
        "connect_timeout": 5,
    }
    
    print(f"尝试连接到 PostgreSQL:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {dbname}")
    print(f"  User: {user}")
    
    return params


def get_connection():
    """
    获取 PostgreSQL 数据库连接。

    从环境变量 DATABASE_URL 中读取数据库连接信息，
    建立并返回一个有效的数据库连接对象。

    Returns:
        psycopg.Connection: PostgreSQL 数据库连接对象。

    Raises:
        psycopg.Error: 当数据库连接失败时抛出异常。
        TimeoutError: 当连接超时时抛出异常。
    """
    try:
        conn_params = get_connection_params()
        print("正在建立连接...")
        conn = psycopg.connect(**conn_params)
        print("✅ 连接成功!")
        return conn
    except psycopg.OperationalError as e:
        print(f"❌ 连接失败: {e}")
        print("\n可能的原因:")
        print("  1. PostgreSQL 服务未启动")
        print("  2. 端口号不正确（当前配置为 5433）")
        print("  3. 数据库不存在")
        print("  4. 用户名或密码错误")
        print("  5. 防火墙阻止连接")
        print("\n请检查:")
        print("  - PostgreSQL 服务是否运行: pg_lsclusters 或 systemctl status postgresql")
        print("  - 端口是否正确: netstat -an | grep 5433")
        print("  - 数据库是否存在: psql -U edudiag -p 5433 -l")
        raise
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        raise



@pytest.fixture
def db_connection():
    """
    提供数据库连接的 pytest fixture。

    为每个测试函数创建独立的数据库连接，并在测试完成后自动关闭连接，
    确保测试之间的隔离性和资源的正确释放。

    Yields:
        psycopg.Connection: 数据库连接对象。
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def clean_test_table(db_connection):
    """
    提供清理后的测试表的 pytest fixture。

    在测试前创建测试表，在测试后删除测试表，
    确保每次测试都在干净的环境中执行。

    Args:
        db_connection: 数据库连接对象。

    Yields:
        psycopg.Connection: 已创建测试表的数据库连接对象。
    """
    cursor = db_connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_study_goals (
                id SERIAL PRIMARY KEY,
                subject VARCHAR(255) NOT NULL,
                target TEXT NOT NULL,
                deadline DATE NOT NULL,
                current_level VARCHAR(100),
                daily_available_minutes INTEGER,
                weekly_available_days INTEGER,
                preferred_methods TEXT[],
                weak_points TEXT[],
                extra_requirements TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db_connection.commit()
        yield db_connection
    finally:
        cursor.execute("DROP TABLE IF EXISTS test_study_goals")
        db_connection.commit()
        cursor.close()


class TestDatabaseConnection:
    """测试数据库连接相关功能"""

    def test_connection_success(self):
        """原因：验证能够成功连接到 PostgreSQL 数据库。"""
        conn = get_connection()
        assert conn is not None
        assert not conn.closed
        conn.close()

    def test_connection_can_execute_query(self, db_connection):
        """原因：验证数据库连接可以正常执行 SQL 查询。"""
        cursor = db_connection.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 1
        cursor.close()

    def test_connection_info(self, db_connection):
        """原因：验证可以获取数据库连接的基本信息。"""
        assert db_connection.info.dbname == "study_planner"
        assert db_connection.info.user == "edudiag"


class TestTableOperations:
    """测试表操作相关功能"""

    def test_create_table(self, db_connection):
        """原因：验证可以成功创建数据表。"""
        cursor = db_connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_temp_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100)
            )
        """)
        db_connection.commit()
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'test_temp_table'
            )
        """)
        exists = cursor.fetchone()[0]
        assert exists is True
        
        cursor.execute("DROP TABLE IF EXISTS test_temp_table")
        db_connection.commit()
        cursor.close()

    def test_drop_table(self, db_connection):
        """原因：验证可以成功删除数据表。"""
        cursor = db_connection.cursor()
        cursor.execute("""
            CREATE TABLE test_drop_table (
                id SERIAL PRIMARY KEY,
                value INTEGER
            )
        """)
        db_connection.commit()
        
        cursor.execute("DROP TABLE test_drop_table")
        db_connection.commit()
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'test_drop_table'
            )
        """)
        exists = cursor.fetchone()[0]
        assert exists is False
        cursor.close()


class TestCRUDOperations:
    """测试基本的 CRUD 操作"""

    def test_insert_single_record(self, clean_test_table):
        """原因：验证可以向表中插入单条记录。"""
        cursor = clean_test_table.cursor()
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, current_level, daily_available_minutes, weekly_available_days)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            "Python 编程",
            "掌握 Python 基础语法",
            date.today() + timedelta(days=30),
            "零基础",
            120,
            5
        ))
        record_id = cursor.fetchone()[0]
        clean_test_table.commit()
        
        assert record_id is not None
        assert isinstance(record_id, int)
        cursor.close()

    def test_insert_with_arrays(self, clean_test_table):
        """原因：验证可以插入包含数组字段的记录。"""
        cursor = clean_test_table.cursor()
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, preferred_methods, weak_points)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            "Java 编程",
            "掌握 Java 核心概念",
            date.today() + timedelta(days=60),
            ["视频教程", "实践项目"],
            ["缺乏编程经验"]
        ))
        record_id = cursor.fetchone()[0]
        clean_test_table.commit()
        
        cursor.execute("SELECT preferred_methods, weak_points FROM test_study_goals WHERE id = %s", (record_id,))
        result = cursor.fetchone()
        assert result[0] == ["视频教程", "实践项目"]
        assert result[1] == ["缺乏编程经验"]
        cursor.close()

    def test_select_single_record(self, clean_test_table):
        """原因：验证可以从表中查询单条记录。"""
        cursor = clean_test_table.cursor()
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, current_level)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            "数学",
            "掌握微积分基础",
            date.today() + timedelta(days=45),
            "中级"
        ))
        record_id = cursor.fetchone()[0]
        clean_test_table.commit()
        
        cursor.execute("""
            SELECT id, subject, target, current_level 
            FROM test_study_goals 
            WHERE id = %s
        """, (record_id,))
        result = cursor.fetchone()
        
        assert result is not None
        assert result[0] == record_id
        assert result[1] == "数学"
        assert result[2] == "掌握微积分基础"
        assert result[3] == "中级"
        cursor.close()

    def test_select_multiple_records(self, clean_test_table):
        """原因：验证可以查询多条记录。"""
        cursor = clean_test_table.cursor()
        
        test_data = [
            ("Python", "学习 Python 基础", date.today() + timedelta(days=30)),
            ("Java", "学习 Java 基础", date.today() + timedelta(days=40)),
            ("C++", "学习 C++ 基础", date.today() + timedelta(days=50)),
        ]
        
        for subject, target, deadline in test_data:
            cursor.execute("""
                INSERT INTO test_study_goals (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (subject, target, deadline))
        
        clean_test_table.commit()
        
        cursor.execute("SELECT COUNT(*) FROM test_study_goals")
        count = cursor.fetchone()[0]
        assert count == 3
        
        cursor.execute("SELECT subject FROM test_study_goals ORDER BY subject")
        subjects = [row[0] for row in cursor.fetchall()]
        assert subjects == ["C++", "Java", "Python"]
        cursor.close()

    def test_update_record(self, clean_test_table):
        """原因：验证可以更新表中的记录。"""
        cursor = clean_test_table.cursor()
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, current_level)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            "英语",
            "通过英语四级",
            date.today() + timedelta(days=90),
            "初级"
        ))
        record_id = cursor.fetchone()[0]
        clean_test_table.commit()
        
        cursor.execute("""
            UPDATE test_study_goals 
            SET current_level = %s, extra_requirements = %s
            WHERE id = %s
        """, ("中级", "需要加强听力训练", record_id))
        clean_test_table.commit()
        
        cursor.execute("""
            SELECT current_level, extra_requirements 
            FROM test_study_goals 
            WHERE id = %s
        """, (record_id,))
        result = cursor.fetchone()
        assert result[0] == "中级"
        assert result[1] == "需要加强听力训练"
        cursor.close()

    def test_delete_record(self, clean_test_table):
        """原因：验证可以删除表中的记录。"""
        cursor = clean_test_table.cursor()
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (
            "物理",
            "掌握力学基础",
            date.today() + timedelta(days=60)
        ))
        record_id = cursor.fetchone()[0]
        clean_test_table.commit()
        
        cursor.execute("DELETE FROM test_study_goals WHERE id = %s", (record_id,))
        clean_test_table.commit()
        
        cursor.execute("SELECT COUNT(*) FROM test_study_goals WHERE id = %s", (record_id,))
        count = cursor.fetchone()[0]
        assert count == 0
        cursor.close()


class TestTransactionManagement:
    """测试事务管理功能"""

    def test_transaction_commit(self, clean_test_table):
        """原因：验证事务可以正确提交。"""
        cursor = clean_test_table.cursor()
        try:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (
                "化学",
                "掌握有机化学基础",
                date.today() + timedelta(days=75)
            ))
            clean_test_table.commit()
            
            cursor.execute("SELECT COUNT(*) FROM test_study_goals")
            count = cursor.fetchone()[0]
            assert count == 1
        finally:
            cursor.close()

    def test_transaction_rollback(self, clean_test_table):
        """原因：验证事务可以正确回滚。"""
        cursor = clean_test_table.cursor()
        try:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (
                "生物",
                "掌握细胞生物学",
                date.today() + timedelta(days=80)
            ))
            
            clean_test_table.rollback()
            
            cursor.execute("SELECT COUNT(*) FROM test_study_goals")
            count = cursor.fetchone()[0]
            assert count == 0
        finally:
            cursor.close()

    def test_partial_transaction_rollback(self, clean_test_table):
        """原因：验证部分操作失败时事务可以回滚到保存点。"""
        cursor = clean_test_table.cursor()
        try:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (
                "历史",
                "了解中国近代史",
                date.today() + timedelta(days=50)
            ))
            
            savepoint_name = "test_savepoint"
            cursor.execute(f"SAVEPOINT {savepoint_name}")
            
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (
                None,
                "这将失败",
                date.today()
            ))
            
            cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            clean_test_table.commit()
            
            cursor.execute("SELECT COUNT(*) FROM test_study_goals")
            count = cursor.fetchone()[0]
            assert count == 1
            
            cursor.execute("SELECT subject FROM test_study_goals")
            subject = cursor.fetchone()[0]
            assert subject == "历史"
        finally:
            cursor.close()


class TestQueryOperations:
    """测试复杂查询操作"""

    def test_query_with_where_clause(self, clean_test_table):
        """原因：验证可以使用 WHERE 子句进行条件查询。"""
        cursor = clean_test_table.cursor()
        
        test_data = [
            ("Python", "零基础", 120),
            ("Java", "初级", 90),
            ("Python", "中级", 150),
        ]
        
        for subject, level, minutes in test_data:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, current_level, daily_available_minutes)
                VALUES (%s, %s, %s)
            """, (subject, level, minutes))
        
        clean_test_table.commit()
        
        cursor.execute("""
            SELECT subject, current_level 
            FROM test_study_goals 
            WHERE subject = %s AND daily_available_minutes > %s
        """, ("Python", 100))
        
        results = cursor.fetchall()
        assert len(results) == 1
        assert results[0][0] == "Python"
        assert results[0][1] == "中级"
        cursor.close()

    def test_query_with_order_by(self, clean_test_table):
        """原因：验证可以使用 ORDER BY 进行排序查询。"""
        cursor = clean_test_table.cursor()
        
        test_data = [
            ("数学", 30),
            ("英语", 60),
            ("物理", 45),
        ]
        
        days_list = [days for _, days in test_data]
        for subject, days in test_data:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, deadline)
                VALUES (%s, %s)
            """, (subject, date.today() + timedelta(days=days)))
        
        clean_test_table.commit()
        
        cursor.execute("""
            SELECT subject 
            FROM test_study_goals 
            ORDER BY deadline ASC
        """)
        
        results = [row[0] for row in cursor.fetchall()]
        assert results == ["数学", "物理", "英语"]
        cursor.close()

    def test_query_with_aggregation(self, clean_test_table):
        """原因：验证可以使用聚合函数进行统计查询。"""
        cursor = clean_test_table.cursor()
        
        test_data = [
            ("Python", 120),
            ("Java", 90),
            ("Python", 150),
            ("Java", 100),
        ]
        
        for subject, minutes in test_data:
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, daily_available_minutes)
                VALUES (%s, %s)
            """, (subject, minutes))
        
        clean_test_table.commit()
        
        cursor.execute("""
            SELECT subject, 
                   COUNT(*) as count,
                   AVG(daily_available_minutes) as avg_minutes
            FROM test_study_goals 
            GROUP BY subject
            ORDER BY subject
        """)
        
        results = cursor.fetchall()
        assert len(results) == 2
        
        java_result = results[0]
        assert java_result[0] == "Java"
        assert java_result[1] == 2
        assert java_result[2] == 95.0
        
        python_result = results[1]
        assert python_result[0] == "Python"
        assert python_result[1] == 2
        assert python_result[2] == 135.0
        cursor.close()


class TestErrorHandling:
    """测试错误处理功能"""

    def test_invalid_sql_syntax(self, db_connection):
        """原因：验证无效 SQL 语法会抛出异常。"""
        cursor = db_connection.cursor()
        with pytest.raises(psycopg.errors.SyntaxError):
            cursor.execute("INVALID SQL STATEMENT")
        cursor.close()

    def test_unique_constraint_violation(self, clean_test_table):
        """原因：验证违反唯一约束时会抛出异常。"""
        cursor = clean_test_table.cursor()
        
        cursor.execute("""
            ALTER TABLE test_study_goals 
            ADD CONSTRAINT unique_subject_target 
            UNIQUE (subject, target)
        """)
        clean_test_table.commit()
        
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline)
            VALUES (%s, %s, %s)
        """, (
            "Python",
            "学习目标A",
            date.today() + timedelta(days=30)
        ))
        clean_test_table.commit()
        
        with pytest.raises(psycopg.errors.UniqueViolation):
            cursor.execute("""
                INSERT INTO test_study_goals 
                (subject, target, deadline)
                VALUES (%s, %s, %s)
            """, (
                "Python",
                "学习目标A",
                date.today() + timedelta(days=60)
            ))
            clean_test_table.commit()
        
        cursor.execute("ALTER TABLE test_study_goals DROP CONSTRAINT unique_subject_target")
        clean_test_table.commit()
        cursor.close()

    def test_not_null_constraint_violation(self, clean_test_table):
        """原因：验证违反非空约束时会抛出异常。"""
        cursor = clean_test_table.cursor()
        
        with pytest.raises(psycopg.errors.NotNullViolation):
            cursor.execute("""
                INSERT INTO test_study_goals 
                (target, deadline)
                VALUES (%s, %s)
            """, (
                "缺少主题字段",
                date.today() + timedelta(days=30)
            ))
            clean_test_table.commit()
        
        cursor.close()


class TestDataTypeHandling:
    """测试数据类型处理"""

    def test_date_type_handling(self, clean_test_table):
        """原因：验证日期类型可以正确存储和读取。"""
        cursor = clean_test_table.cursor()
        test_date = date(2025, 12, 31)
        
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline)
            VALUES (%s, %s, %s)
            RETURNING deadline
        """, (
            "测试科目",
            "测试目标",
            test_date
        ))
        
        returned_date = cursor.fetchone()[0]
        clean_test_table.commit()
        
        assert returned_date == test_date
        assert isinstance(returned_date, date)
        cursor.close()

    def test_array_type_handling(self, clean_test_table):
        """原因：验证数组类型可以正确存储和读取。"""
        cursor = clean_test_table.cursor()
        
        methods = ["视频", "书籍", "实践"]
        weak_points = ["语法", "算法"]
        
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, preferred_methods, weak_points)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING preferred_methods, weak_points
        """, (
            "JavaScript",
            "掌握前端开发",
            date.today() + timedelta(days=90),
            methods,
            weak_points
        ))
        
        returned_methods, returned_weak_points = cursor.fetchone()
        clean_test_table.commit()
        
        assert returned_methods == methods
        assert returned_weak_points == weak_points
        assert isinstance(returned_methods, list)
        assert isinstance(returned_weak_points, list)
        cursor.close()

    def test_text_type_handling(self, clean_test_table):
        """原因：验证长文本类型可以正确存储和读取。"""
        cursor = clean_test_table.cursor()
        
        long_text = "这是一个很长的文本内容。" * 100
        
        cursor.execute("""
            INSERT INTO test_study_goals 
            (subject, target, deadline, extra_requirements)
            VALUES (%s, %s, %s, %s)
            RETURNING extra_requirements
        """, (
            "长篇测试",
            "测试长文本存储",
            date.today() + timedelta(days=60),
            long_text
        ))
        
        returned_text = cursor.fetchone()[0]
        clean_test_table.commit()
        
        assert returned_text == long_text
        assert len(returned_text) == len(long_text)
        cursor.close()


if __name__ == "__main__":
    print(get_connection())