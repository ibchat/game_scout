# Trends Pipeline Debug Log

## Step A - Reality Check

## Git Status
On branch 2026-01-19-u3c4
Untracked files:
  (use "git add <file>..." to include in what will be committed)
	DEBUG_TRENDS_PIPELINE.md

nothing added to commit but untracked files present (use "git add" to track)

## Git Log
30f77f9 Fix: reduce collect limit to 100 (API constraint)
97402ec Add Trends Scout seeding and pipeline scripts
eab9aa6 Fix: register trends_v1 router in main.py
4046c85 Fix Trends Scout: use real numeric signals, exclude evergreen giants
34e0ca2 Fix trends aggregation: align reviews & positivity with steam_review_daily

## Docker Compose Status
time="2026-01-25T08:22:44+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
NAME                    IMAGE                COMMAND                  SERVICE    CREATED       STATUS                PORTS
game_scout-api-1        game_scout-api       "uvicorn apps.api.ma…"   api        2 days ago    Up 8 hours            0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
game_scout-beat-1       game_scout-beat      "celery -A apps.work…"   beat       2 days ago    Up 2 days             
game_scout-postgres-1   postgres:15-alpine   "docker-entrypoint.s…"   postgres   10 days ago   Up 9 days (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
game_scout-redis-1      redis:7-alpine       "docker-entrypoint.s…"   redis      10 days ago   Up 9 days (healthy)   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
game_scout-worker-1     game_scout-worker    "celery -A apps.work…"   worker     2 days ago    Up 2 days             

## Worker Logs (last 200)
time="2026-01-25T08:22:45+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
worker-1  | /usr/local/lib/python3.12/site-packages/celery/platforms.py:841: SecurityWarning: You're running the worker with superuser privileges: this is
worker-1  | absolutely not recommended!
worker-1  | 
worker-1  | Please specify a different user using the --uid option.
worker-1  | 
worker-1  | User information: uid=0 euid=0 gid=0 egid=0
worker-1  | 
worker-1  |   warnings.warn(SecurityWarning(ROOT_DISCOURAGED.format(
worker-1  |  
worker-1  |  -------------- celery@bb6322b26a59 v5.6.2 (recovery)
worker-1  | --- ***** ----- 
worker-1  | -- ******* ---- Linux-6.12.54-linuxkit-aarch64-with-glibc2.41 2026-01-22 10:26:06
worker-1  | - *** --- * --- 
worker-1  | - ** ---------- [config]
worker-1  | - ** ---------- .> app:         game_scout_worker:0xffff95aaa150
worker-1  | - ** ---------- .> transport:   redis://redis:6379/0
worker-1  | - ** ---------- .> results:     redis://redis:6379/0
worker-1  | - *** --- * --- .> concurrency: 8 (prefork)
worker-1  | -- ******* ---- .> task events: ON
worker-1  | --- ***** ----- 
worker-1  |  -------------- [queues]
worker-1  |                 .> celery           exchange=celery(direct) key=celery
worker-1  |                 
worker-1  | 
worker-1  | [tasks]
worker-1  |   . analyze_reddit_trends
worker-1  |   . analyze_youtube_trends
worker-1  |   . apps.worker.tasks.collect_relaunch_steam.collect_relaunch_steam_task
worker-1  |   . calculate_weekly_aggregates
worker-1  |   . collect_reddit_trends
worker-1  |   . collect_tiktok_trends
worker-1  |   . collect_twitter_trends
worker-1  |   . collect_youtube_comments
worker-1  |   . collect_youtube_trends
worker-1  |   . generate_trend_queries
worker-1  |   . relaunch.compute_scores
worker-1  |   . save_daily_snapshot
worker-1  | 
worker-1  | [2026-01-22 10:26:06,775: INFO/MainProcess] Connected to redis://redis:6379/0
worker-1  | [2026-01-22 10:26:06,778: INFO/MainProcess] mingle: searching for neighbors
worker-1  | [2026-01-22 10:26:07,790: INFO/MainProcess] mingle: all alone
worker-1  | [2026-01-22 10:26:07,808: INFO/MainProcess] celery@bb6322b26a59 ready.

## API Logs (last 200)
time="2026-01-25T08:22:45+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
api-1  | WARNING:  WatchFiles detected changes in 'apps/api/main.py'. Reloading...
api-1  | Process SpawnProcess-2:
api-1  | Traceback (most recent call last):
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 314, in _bootstrap
api-1  |     self.run()
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 108, in run
api-1  |     self._target(*self._args, **self._kwargs)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/_subprocess.py", line 78, in subprocess_started
api-1  |     target(sockets=sockets)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 62, in run
api-1  |     return asyncio.run(self.serve(sockets=sockets))
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
api-1  |     return runner.run(main)
api-1  |            ^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
api-1  |     return self._loop.run_until_complete(task)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 69, in serve
api-1  |     config.load()
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/config.py", line 458, in load
api-1  |     self.loaded_app = import_from_string(self.app)
api-1  |                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/importer.py", line 21, in import_from_string
api-1  |     module = importlib.import_module(module_str)
api-1  |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
api-1  |     return _bootstrap._gcd_import(name[level:], package, level)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
api-1  |   File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
api-1  |   File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
api-1  |   File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
api-1  |   File "<frozen importlib._bootstrap_external>", line 999, in exec_module
api-1  |   File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
api-1  |   File "/app/apps/api/main.py", line 71, in <module>
api-1  |     app.include_router(trends_v1.router, prefix=API_V1)
api-1  |                                                 ^^^^^^
api-1  | NameError: name 'API_V1' is not defined
api-1  | INFO:     Stopping reloader process [1]
api-1  | INFO:     Will watch for changes in these directories: ['/app']
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
api-1  | INFO:     Started reloader process [1] using WatchFiles
api-1  | Process SpawnProcess-1:
api-1  | Traceback (most recent call last):
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 314, in _bootstrap
api-1  |     self.run()
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 108, in run
api-1  |     self._target(*self._args, **self._kwargs)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/_subprocess.py", line 78, in subprocess_started
api-1  |     target(sockets=sockets)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 62, in run
api-1  |     return asyncio.run(self.serve(sockets=sockets))
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
api-1  |     return runner.run(main)
api-1  |            ^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
api-1  |     return self._loop.run_until_complete(task)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 69, in serve
api-1  |     config.load()
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/config.py", line 458, in load
api-1  |     self.loaded_app = import_from_string(self.app)
api-1  |                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/importer.py", line 21, in import_from_string
api-1  |     module = importlib.import_module(module_str)
api-1  |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
api-1  |     return _bootstrap._gcd_import(name[level:], package, level)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
api-1  |   File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
api-1  |   File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
api-1  |   File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
api-1  |   File "<frozen importlib._bootstrap_external>", line 999, in exec_module
api-1  |   File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
api-1  |   File "/app/apps/api/main.py", line 71, in <module>
api-1  |     app.include_router(trends_v1.router, prefix=API_V1)
api-1  |                                                 ^^^^^^
api-1  | NameError: name 'API_V1' is not defined
api-1  | INFO:     Stopping reloader process [1]
api-1  | INFO:     Will watch for changes in these directories: ['/app']
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
api-1  | INFO:     Started reloader process [1] using WatchFiles
api-1  | Process SpawnProcess-1:
api-1  | Traceback (most recent call last):
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 314, in _bootstrap
api-1  |     self.run()
api-1  |   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 108, in run
api-1  |     self._target(*self._args, **self._kwargs)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/_subprocess.py", line 78, in subprocess_started
api-1  |     target(sockets=sockets)
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 62, in run
api-1  |     return asyncio.run(self.serve(sockets=sockets))
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
api-1  |     return runner.run(main)
api-1  |            ^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
api-1  |     return self._loop.run_until_complete(task)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/server.py", line 69, in serve
api-1  |     config.load()
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/config.py", line 458, in load
api-1  |     self.loaded_app = import_from_string(self.app)
api-1  |                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/site-packages/uvicorn/importer.py", line 21, in import_from_string
api-1  |     module = importlib.import_module(module_str)
api-1  |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
api-1  |     return _bootstrap._gcd_import(name[level:], package, level)
api-1  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
api-1  |   File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
api-1  |   File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
api-1  |   File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
api-1  |   File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
api-1  |   File "<frozen importlib._bootstrap_external>", line 999, in exec_module
api-1  |   File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
api-1  |   File "/app/apps/api/main.py", line 71, in <module>
api-1  |     app.include_router(trends_v1.router, prefix=API_V1)
api-1  |                                                 ^^^^^^
api-1  | NameError: name 'API_V1' is not defined
api-1  | WARNING:  WatchFiles detected changes in 'apps/api/main.py'. Reloading...
api-1  | INFO:     Started server process [10]
api-1  | INFO:     Waiting for application startup.
api-1  | INFO:     Application startup complete.
api-1  | INFO:     Shutting down
api-1  | INFO:     Waiting for application shutdown.
api-1  | INFO:     Application shutdown complete.
api-1  | INFO:     Finished server process [10]
api-1  | INFO:     Stopping reloader process [1]
api-1  | INFO:     Will watch for changes in these directories: ['/app']
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
api-1  | INFO:     Started reloader process [1] using WatchFiles
api-1  | INFO:     Started server process [8]
api-1  | INFO:     Waiting for application startup.
api-1  | INFO:     Application startup complete.
api-1  | INFO:     172.18.0.1:60814 - "GET /api/v1/trends/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:60818 - "POST /api/v1/trends/admin/ingest_reviews?days_back=0 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:60824 - "POST /api/v1/trends/admin/aggregate?days_back=7 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:55748 - "GET /api/v1/trends/games/emerging?limit=50 HTTP/1.1" 200 OK
api-1  | WARNING:  WatchFiles detected changes in 'apps/api/main.py'. Reloading...
api-1  | INFO:     Shutting down
api-1  | INFO:     Waiting for application shutdown.
api-1  | INFO:     Application shutdown complete.
api-1  | INFO:     Finished server process [8]
api-1  | INFO:     Started server process [11]
api-1  | INFO:     Waiting for application startup.
api-1  | INFO:     Application startup complete.
api-1  | INFO:     172.18.0.1:59592 - "GET /dashboard HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/analytics/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59604 - "GET /apple-touch-icon-precomposed.png HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:59626 - "GET /favicon.ico HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:59610 - "GET /apple-touch-icon.png HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/analytics/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:59592 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:63586 - "GET /api/v1/trends/games/emerging?limit=20 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57290 - "POST /api/v1/trends/admin/collect?limit=500 HTTP/1.1" 422 Unprocessable Entity
api-1  | INFO:     172.18.0.1:57304 - "POST /api/v1/trends/admin/ingest_reviews?days_back=0 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57306 - "POST /api/v1/trends/admin/aggregate?days_back=7 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62468 - "GET /api/v1/trends/games/emerging?limit=20 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /dashboard HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/analytics/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56410 - "GET /apple-touch-icon-precomposed.png HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:56418 - "GET /favicon.ico HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:56420 - "GET /apple-touch-icon.png HTTP/1.1" 404 Not Found
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/analytics/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:56406 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/games/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/games/list?limit=50 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/reddit/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/reddit/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/youtube/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/youtube/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/reddit/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/reddit/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/games/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/games/list?limit=50 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:62268 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57736 - "GET /api/v1/yearly/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57736 - "GET /api/v1/yearly/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57736 - "GET /api/v1/relaunch/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:57736 - "GET /api/v1/relaunch/candidates?min_score=0&limit=200 HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/yearly/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/yearly/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/youtube/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/youtube/summary HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/reddit/health HTTP/1.1" 200 OK
api-1  | INFO:     172.18.0.1:58398 - "GET /api/v1/reddit/summary HTTP/1.1" 200 OK

## Worker Process Check
time="2026-01-25T08:22:45+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
sh: 1: ps: not found
Worker not accessible

## Worker Command
time="2026-01-25T08:22:46+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
/usr/local/bin/python3.12 /usr/local/bin/celery -A apps.worker.celery_app worker --loglevel=info 
## Trend Jobs Status
time="2026-01-25T08:22:46+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
   job_type    | status  | cnt 
---------------+---------+-----
 appdetails    | queued  |   3
 appdetails    | success |  13
 players       | success |   9
 reviews_daily | queued  |   3
 reviews_daily | success |  12
(5 rows)


## Pipeline Counts
time="2026-01-25T08:22:47+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
ERROR:  relation "trend_seed_apps" does not exist
LINE 1: select (select count(*)::int from trend_seed_apps where is_a...
                                          ^

## Step B-H: Fixes Applied

### Fixed Issues:
1. API main.py: Fixed API_V1 undefined error (moved trends_v1 router registration)
2. Created apps/worker/tasks/trends_jobs.py: Worker processor for trend_jobs table
3. Added worker_trends service to docker-compose.yml
4. Fixed steam_review_daily schema mismatch (all_positive_percent as INTEGER)
5. Fixed loop to run continuously (not exit on no jobs)
6. Created scripts/probe_steam_from_worker.sh
7. Created scripts/verify_trends_pipeline.sh
8. Updated seed SQL to prefer non-evergreen candidates

### Current Status:
time="2026-01-25T08:32:07+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
   job_type    |   status   | count 
---------------+------------+-------
 appdetails    | failed     |    58
 appdetails    | processing |     1
 appdetails    | queued     |    41
 reviews_daily | processing |     1
 reviews_daily | queued     |    22
 reviews_daily | success    |    77
(6 rows)


time="2026-01-25T08:32:08+01:00" level=warning msg="/Users/mariya/Desktop/game_scout/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
 count 
-------
    78
(1 row)


