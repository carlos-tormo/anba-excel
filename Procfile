web: bash -lc 'if [ ! -f /data/league.db ]; then mkdir -p /data && cp data/league.db /data/league.db; fi; python app/server.py --db /data/league.db --host 0.0.0.0 --port ${PORT:-8000}'
