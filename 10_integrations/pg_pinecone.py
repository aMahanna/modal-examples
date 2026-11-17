# ---
# lambda-test: false  # missing-secret
# ---

# # Search Postgres with pg_pinecone

# This example runs a vector search from Modal against Postgres.
# The rows stay in Postgres, and the query is the same SQL as
# [pgvector](https://github.com/pgvector/pgvector).
# [pg_pinecone](https://github.com/pinecone-io/pg_pinecone) serves that query
# with a `native` index.

# ## Database

# You bring the database. It needs the `vector` and `pg_pinecone` extensions,
# and the database user needs to be allowed to create them.
# The [`pineconeteam/pg_pinecone`](https://hub.docker.com/r/pineconeteam/pg_pinecone)
# image is Postgres with both extensions installed.
# The [pg_pinecone docs](https://docs.pinecone.io/guides/pg-pinecone/overview)
# cover setup.

# Modal connects to that database over the network. Put the connection in a
# [Secret](https://modal.com/docs/guide/secrets). In the Modal dashboard, create
# a secret with the **Postgres compatible** preset and name it `pg-pinecone`.

import modal

app = modal.App("example-pg-pinecone")

pg_secret = modal.Secret.from_name(
    "pg-pinecone",
    required_keys=["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev")
    .uv_pip_install("psycopg2~=2.9.9")
)

# ## Search

# `psycopg2` reads `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`
# from the secret. The function replaces a table named `modal_pg_pinecone_docs`,
# builds a `native` index, and searches with pgvector's cosine distance
# operator, `<=>`.
#
# The query vector points at the first of the three dimensions. The closest
# rows are the two whose vectors point the same way.


@app.function(image=image, secrets=[pg_secret], timeout=180)
def search():
    import psycopg2

    conn = psycopg2.connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_pinecone")
    cur.execute("DROP TABLE IF EXISTS modal_pg_pinecone_docs")
    cur.execute(
        """
        CREATE TABLE modal_pg_pinecone_docs (
            id bigint PRIMARY KEY,
            body text,
            embedding vector(3)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO modal_pg_pinecone_docs (id, body, embedding) VALUES
            (1, 'The Eiffel Tower was completed in 1889.', '[0.1, 0.1, 0.9]'),
            (2, 'Photosynthesis converts sunlight into glucose.', '[0.05, 0.9, 0.1]'),
            (4, 'Espresso is brewed by forcing hot water through ground coffee.', '[0.95, 0.05, 0.05]'),
            (7, 'A croissant is a flaky pastry made from buttered dough.', '[0.95, 0.05, 0.1]')
        """
    )
    cur.execute(
        "SELECT pinecone.create_index("
        "'modal_pg_pinecone_docs', 'embedding', engine => 'native')"
    )
    cur.execute("SET enable_seqscan = off")
    cur.execute(
        """
        SELECT id, body
        FROM modal_pg_pinecone_docs
        ORDER BY embedding <=> '[1, 0, 0]'
        LIMIT 2
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


@app.local_entrypoint()
def main():
    for row in search.remote():
        print(row)
