"""Serve retained articles and isolated Mock WordPress delivery; no API keys loaded."""
import argparse
from pathlib import Path

import uvicorn

from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.saved_article import SavedArticleGeneration


def compose(directory):
    directory = Path(directory).resolve()
    app = create_app(mvp_dir=directory, db_path=directory / 'offline-demo.sqlite3',
                     live_db_path=directory / 'offline-live.sqlite3')
    app.state.mvp_service.generation = SavedArticleGeneration(app.state.mvp_service)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('.data/seo-mvp'))
    parser.add_argument('--port', type=int, default=8012)
    args = parser.parse_args()
    uvicorn.run(compose(args.directory), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
