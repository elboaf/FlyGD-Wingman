"""The Uploader runtime: the recording list, YouTube uploads, combat-log posts.

`controller.py` owns the state the Uploader route runs on; `gate.py` holds
the work gate that the uploader SHARES with the app updater and Quit. The
pure modules this runtime drives (`uploader`, `stitch`, `combatlog`,
`discord`, `library`, `durations`, `links`, `watcher`) stay at the package
top level, as they were.
"""
