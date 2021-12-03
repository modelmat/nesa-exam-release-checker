NESA Exam Release Checker
=========================

This is a (very basic) script + webserver combination that logs whenever NESA's exam list website updates.
This allows you to track when new exams get added or the solutions get added, which is "useful" during the examination period each year.

By default, the script checks the website every 1h, although it only logs changes accurate to a day.
It is possible to figure out which hour that an update was found through the `output/backend.log` file but this isn't shown anywhere.

Note, this script is NOT safe to run for the open internet.
There is little to no verification of how URLs are parsed, and Python's SimpleHTTPServer also notes that it is insecure.

Setup
-----

1. Create a folder "output" in the repo

2. Install the two `.service` and single `.timer` files to `~/.local/share/systemd/user/`.
   You will likely need to change the directories of where the script is saved two, and the username.

3. Enable `nesa-server.service` and start `nesa-downloader.timer` using `systemd --user`.


