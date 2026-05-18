# coding=utf-8
import sys

sys.path.append("/data/airflow-dags/dags")
import pandas as pd
from common import datasource, sync_data as sd
from common.utils.sql_util import read_sql_file

"""
    每日装载V0版本库存监控底表数据
"""

# 1. 先执行前置sql
def load_pre_sql():
    sql = read_sql_file('/data/airflow-dags/dags/dw/ads/sql/warehouse_monitor_report/a_pre_sql.sql')
    # sql = read_sql_file('../sql/warehouse_monitor_report/a_pre_sql.sql')
    sd.execute_sql(
        ds=datasource.DW_LEANG,
        db='dw_leang',
        sql=sql,
    )

# 2. 处理批次断货风险
def load_batch_out_of_stock_risk():
    # 转为字典，从数据库获取temp_lingxing_kucu_pici数据
    df = sd.read_sql(
        ds=datasource.DW_LEANG,
        sql="""
            select * from temp_lingxing_kucu_pici;
        """
    )
    data = df.to_dict(orient="records")
    if data:
        warehouse_util(data)


def warehouse_util(data):
    df = pd.DataFrame(data)
    # 数据预处理
    df["batch_num"] = pd.to_numeric(df["batch_num"], errors="coerce").fillna(0)
    df["put_num"] = pd.to_numeric(df["put_num"], errors="coerce").fillna(0)
    df["jieyu_kucun"] = pd.to_numeric(df["jieyu_kucun"], errors="coerce").fillna(0)

    # 计算余额库存
    result = df.groupby(["FNSKU", "store_name", "type"], group_keys=False).apply(compute_balance)

    # 返回excel
    # return result.to_dict(orient="records")

    column_defs = []
    for i, col in enumerate(result.columns):
        # 处理列名中的空格或特殊字符
        col_name = f"`{col}`" if ' ' in col or '-' in col else col

        col_type = "VARCHAR(128)"

        column_defs.append(f"{col_name} {col_type}")

    create_sql = f"""
                    DROP TABLE IF EXISTS temp_batch_kucun;
                    CREATE TABLE temp_batch_kucun (
                        {', '.join(column_defs)}
                    )
                   ENGINE=OLAP
                   DUPLICATE KEY({', '.join([f'`{col}`' if ' ' in col or '-' in col else col for col in df.columns[:1]])})
                   DISTRIBUTED BY HASH({df.columns[0]}) BUCKETS 2
                   PROPERTIES (
                       "replication_num" = "1"
                   )
                """

    sd.write_to_doris(
        ds=datasource.DW_LEANG,
        db='dw_leang',
        table='temp_batch_kucun',
        df=result,
        create_tbl=create_sql
    )

def compute_balance(group):
    group = group.sort_values("put_date").copy()
    balances = []
    prev_balance = group.iloc[0]["jieyu_kucun"]
    sale_num = group.iloc[0]["batch_num"]

    for i, row in enumerate(group.itertuples()):
        if i == 0:
            balance = prev_balance
        else:
            # 上批次销量
            balance = prev_balance + row.put_num - sale_num

        # 如果结余库存为负数，设为0
        if balance < 0:
            balance = 0

        balances.append(balance)
        prev_balance = balance
        sale_num = row.batch_num

    group["jieyu_kucun"] = balances
    return group


# 3. 生成库存监控底表
def load_warehouse_monitor_report():
    sql = read_sql_file('/data/airflow-dags/dags/dw/ads/sql/warehouse_monitor_report/b_post_sql.sql')
    # sql = read_sql_file('../sql/warehouse_monitor_report/b_post_sql.sql')
    sd.execute_sql(
        ds=datasource.DW_LEANG,
        db='dw_leang',
        sql=sql,
    )

# 4.处理未来FBA库存预测
def load_fba_warehouse_prediction():
    sql = read_sql_file('/data/airflow-dags/dags/dw/ads/sql/warehouse_monitor_report/c_post_sql.sql')
    # sql = read_sql_file('../sql/warehouse_monitor_report/c_post_sql.sql')
    sd.execute_sql(
        ds=datasource.DW_LEANG,
        db='dw_leang',
        sql=sql,
    )

def run_load_all_warehouse_task():
    print("开始加载所有仓库数据")
    load_pre_sql()
    print("开始处理批次断货风险")
    load_batch_out_of_stock_risk()
    print("开始生成库存监控底表")
    load_warehouse_monitor_report()
    print("开始处理未来FBA库存预测")
    load_fba_warehouse_prediction()
    print("所有仓库数据加载完成")


if __name__ == '__main__':
    run_load_all_warehouse_task()