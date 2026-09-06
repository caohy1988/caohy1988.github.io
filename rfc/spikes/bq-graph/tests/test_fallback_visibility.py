"""Execute the shipped fallback joins offline; only array/table syntax is adapted."""
import json
import sqlite3
from pathlib import Path

import pytest


def walk(hidden=None, foreign=None):
    sql = (Path(__file__).resolve().parents[1] / "sql/fallback.sql").read_text()
    sql = sql.replace('`{ds}.edges`', 'edges').replace('`{ds}.nodes`', 'nodes')
    sql = sql.replace('IN UNNEST(@seeds)', 'IN (SELECT value FROM json_each(@seeds))')
    for value in ('e.edge_id', 'seed, n1', 'seed, n1, n2'):
        sql = sql.replace(f'[{value}]', f'json_array({value})')
    with sqlite3.connect(':memory:') as db:
        db.row_factory = sqlite3.Row
        db.create_function('ARRAY_CONCAT', 2, lambda a, b: json.dumps(json.loads(a) + json.loads(b)))
        db.execute('CREATE TABLE nodes(node_id, status, publication_id, path, kind, type, stub)')
        db.execute('CREATE TABLE edges(edge_id, src_id, dst_id, publication_id, relation)')
        for node, status, kind in [('seed', 'deprecated', 'Metric'), ('middle', 'stable', 'Metric'),
                                   ('computation', 'stable', 'Attested Computation')]:
            if node != hidden:
                db.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',
                           (node, status, 'other' if node == foreign else 'pin', node + '.md', 'Concept', kind, False))
        # Node-only denial deliberately leaves both incident edges visible.
        db.executemany('INSERT INTO edges VALUES(?,?,?,?,?)', [
            ('first', 'seed', 'middle', 'pin', 'LINKS_TO'),
            ('second', 'middle', 'computation', 'pin', 'LINKS_TO')])
        return [dict(row) for row in db.execute(sql, {'seeds': '["seed"]', 'publication_id': 'pin'})]


def test_visible_pinned_two_hop_fallback_returns_computation():
    rows = walk()
    assert len(rows) == 1
    assert rows[0]['computation_id'] == 'computation'
    assert json.loads(rows[0]['hop_ids']) == ['seed', 'middle', 'computation']
    assert json.loads(rows[0]['edge_ids']) == ['first', 'second']


@pytest.mark.parametrize('endpoint', ['seed', 'middle', 'computation'])
@pytest.mark.parametrize('denial', ['hidden', 'foreign'])
def test_fallback_requires_visible_pinned_rows_at_every_endpoint(endpoint, denial):
    assert walk(**{denial: endpoint}) == []
