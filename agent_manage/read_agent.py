from typing import Any, Generator

from agno.agent import Agent, get_agent_by_id
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import db_config


def _quote_ident(ident: str) -> str:
    # Minimal escaping for schema/table identifiers in raw SQL.
    return f"\"{ident.replace('\"', '\"\"')}\""


def read_agent() -> Generator[Agent | None, Any, None]:
    try:
        agno_id_list = []
        engine = create_engine(db_config.get_db_url())
        Session = sessionmaker(bind=engine)
        with Session() as session:
            # Resolve schema first to avoid search_path differences between users/tools.
            schema_row = session.execute(
                text(
                    """
                    SELECT table_schema
                    FROM information_schema.tables
                    WHERE table_name = 'agno_components'
                      AND table_type = 'BASE TABLE'
                    ORDER BY (table_schema = 'public') DESC, table_schema
                    LIMIT 1;
                    """
                )
            ).fetchone()

            if not schema_row:
                print("Agnet读取提示：数据库中未找到 agno_components 表，视为当前没有已保存的 Agent")
                return

            schema = schema_row[0]
            sql_query = text(f"SELECT component_id FROM {_quote_ident(schema)}.agno_components;")
            query_results = session.execute(sql_query).fetchall()
            agno_id_list = [result[0] for result in query_results]

        print(f"成功在DB中读取到 {len(agno_id_list)} 个 Agent")
        for agent_id in agno_id_list:
            print(f"已加载{agent_id}")
            agent = get_agent_by_id(db=db_config.create_base_db(id=agent_id), id=agent_id)
            yield agent
    except Exception as e:
        print(f"Agnet读取失败：\n{e}")
        yield None
