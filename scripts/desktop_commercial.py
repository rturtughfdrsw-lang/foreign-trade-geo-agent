"""Local read-only Commercial Dev composition; no model or delivery ports."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from foreign_trade_geo_agent.web.commercial_inspector import create_commercial_app


def check_database(path):
    if not path.is_absolute() or not path.is_file():
        raise ValueError('Existing Commercial history database is required')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',):
            raise ValueError('History database integrity failed')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8003)
    parser.add_argument('--instance')
    parser.add_argument('--check-database',action='store_true')
    args=parser.parse_args()
    expected=PROJECT/'.data/seo-mvp/candidate/history.sqlite3'
    if args.database.resolve()!=expected:
        parser.error('Commercial Dev only reads its own identified history database')
    check_database(args.database)
    if args.check_database:
        print('Commercial Dev: existing read-only history and inspector verified.')
        return
    if not args.instance or not 1024<=args.port<=65535:
        parser.error('Launcher instance and valid loopback port required')
    import uvicorn
    uvicorn.run(create_commercial_app(PROJECT,instance=args.instance),host='127.0.0.1',port=args.port,
                workers=1,access_log=False,proxy_headers=False)


if __name__=='__main__':
    main()
