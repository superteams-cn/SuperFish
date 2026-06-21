"""数据访问层（Repository）。

唯一持有 ``session_scope`` 与 ORM 查询的地方：每个实体一个 repo，
对外只收发领域对象（domain/），不泄露 ORM Row，避免会话关闭后的 detached 访问。
services 通过 repository 存取数据，不再直接打开数据库会话。
"""
