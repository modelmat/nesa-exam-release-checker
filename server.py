import subprocess

import http.server
import copy
import datetime
import email.utils
import html
import http.client
import io
import mimetypes
import os
import posixpath
import select
import shutil
import socket # For gethostbyaddr()
import socketserver
import sys
import time
import urllib.parse
import contextlib
from functools import partial
from http import HTTPStatus

import nesa_checker
from datetime import datetime, timedelta


class Server(http.server.BaseHTTPRequestHandler):

    """Simple HTTP request handler with GET and HEAD commands.

    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method.

    The GET and HEAD requests are identical except that the HEAD
    request omits the actual contents of the file.

    """

    server_version = "NesaCheckerV1.0"

    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = os.getcwd()
        self.directory = os.fspath(directory)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Serve a GET request."""
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()

    def send_head(self):
        today = datetime.today()
        yesterday = today - timedelta(days=1)

        parts = urllib.parse.urlsplit(self.path)
        path = parts.path
        query = parts.query

        if query:
            try:
                index = int(query)
                assert index >= 0
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid query: integer only")
                return None
            except AssertionError:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid query: positive integer only")
                return None
        else:
            index = 0
            

        if path == "/":
            return self.prepare_page(nesa_checker.get_subject_list_updates())


        elif path.startswith("/exam-list"):
            indices = {i: s for (i, s) in enumerate(reversed(nesa_checker.find_subject_lists()))}
            diff_date = indices[index]
            print(indices)
            prev_diff_date_raw = None

            if index == len(indices)-1:
                # Current index is oldest (so first entry)
                header = "Exam List: Oldest"
            else:
                if index+1 == len(indices)-1:
                    # Previous diff is oldest diff
                    prev_diff_date = "Oldest"
                else:
                    prev_diff_date = indices[index + 1]

                prev_diff_date_raw = indices[index+1]

                
                header = "Exam List: {} vs {}".format(diff_date, prev_diff_date)

            

            return self.prepare_page(
                nesa_checker.compare_subjects_list(prev_diff_date_raw, diff_date),
                header,
                footer=indices
            )

        elif path.startswith("/subject"):
            subject = path.replace("/subject/", "").replace("-", " ").title()
            indices = nesa_checker.get_indices(subject)
            diff_date = indices[index]

            subj_html = '<a href="{}">{}</a>'.format(nesa_checker.get_url_for_subject(subject), subject)

            if index == len(indices)-1:
                # Current index is oldest (so first entry)
                header = "{}: Oldest".format(subj_html)
            else:
                if index+1 == len(indices)-1:
                    # Previous diff is oldest diff
                    prev_diff_date = "Oldest"
                else:
                    prev_diff_date = indices[index + 1]

                
                header = "{}: {} vs {}".format(subj_html, diff_date, prev_diff_date)

            return self.prepare_page(
                nesa_checker.fetch_diff(subject, index),
                header,
                footer=indices
            )

        elif path == "/status":
            last_check = nesa_checker.get_time_of_last_check()
            return self.prepare_page("""\
<p>Last status check: {}</p>
<p>Current time: {}</p>
<p>Minutes since last check: {:.1f}</p>

<a href="{}">Rerun page downloads (only available after 15 minutes)</a>

<p>Download service logs:</p>
<pre>{}</pre>

<p>Download service status:</p>
<pre>{}</pre>
<pre>{}</pre>

<p>Server logs:</p>
<pre>{}</pre>
""".format(
    last_check,
    datetime.now(),
    nesa_checker.time_elapsed() / 60,
    "/rerun" if nesa_checker.has_update_time_elapsed() else "/rerun-timed",
    nesa_checker.get_latest_log_output(),
    subprocess.run(["systemctl", "--user", "status", "nesa-downloader.timer"], stdout=subprocess.PIPE).stdout.decode("utf-8"),
    subprocess.run(["systemctl", "--user", "status", "nesa-downloader.service"], stdout=subprocess.PIPE).stdout.decode("utf-8"),
    subprocess.run(["systemctl", "--user", "status", "nesa-server.service"], stdout=subprocess.PIPE).stdout.decode("utf-8"),
), "Status", raw=False)

        elif path == "/rerun":
            if nesa_checker.has_update_time_elapsed():
                subprocess.run(["systemctl", "--user" , "start", "--no-block", "nesa-downloader.service"])
#                nesa_checker.download() # or rerun the systemd script
            else:
                return self.redirect_to("/rerun-timed")
             
            return self.redirect_to("/status")

        elif path == "/rerun-timed":
            return self.prepare_page("It has been less than 15 minutes since the last run", "Rerun Denied")
            

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "path not found")
            return None

    def redirect_to(self, url):
        self.send_response(HTTPStatus.FOUND) # 302
        # don't want 301 cause it gets cached
        parts = urllib.parse.urlsplit(self.path)
        new_parts = (parts[0], parts[1], url, "", "")
        new_url = urllib.parse.urlunsplit(new_parts)
        self.send_header("Location", new_url)
        self.end_headers()
        return None

    def prepare_page(self, information=None, page_subtitle=None, raw=True, footer=None):
        r = []

        enc = sys.getfilesystemencoding()
        title = 'NESA Exam Release Checker'
        if page_subtitle:
            title += ": " + page_subtitle
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('''\
<style>
a { color: #0000EE }

.greyed { color: grey }
</style>''')
        # datatables
        r.append('<link rel="stylesheet" href="//cdn.datatables.net/1.11.3/css/jquery.dataTables.min.css">')
        r.append('<script src="https://code.jquery.com/jquery-3.6.0.js" integrity="sha256-H+K7U5CnXl1h5ywQfKtSj8PCmoN9aaq30gDh27Xc0jk=" crossorigin="anonymous"></script>')
        r.append('<script src="//cdn.datatables.net/1.11.3/js/jquery.dataTables.min.js"></script>')
        r.append('''\
<script>
$(document).ready( function () {
    $('#myTable').DataTable( {
        paging: false,
        order: [[2, "desc"], [0, "asc"]]
    } );
} );
</script>''')

        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        if self.path != "/":
            r.append('<a href="/">Back to Main Page</a>')
        if self.path != "/status":
            r.append('<a href="/status">Go to Status Page</a>')

        r.append('<a href="https://educationstandards.nsw.edu.au/wps/portal/nesa/resource-finder/hsc-exam-papers/2021/">2021 Papers</a>')
        r.append('<a href="exam-list">List of Subjects</a>')
        r.append('<hr>\n')

        if isinstance(information, dict):
            r.append('''\
<table id="myTable" class="stripe">
<thead>
<tr>
  <th>Subject</td>
  <th>Added</td>
  <th>Last Update</td>
</tr>
</thead>
<tbody>
''')
            list_subj = sorted(information.items(), key=lambda x: x[0])
            list_subj.sort(key=lambda x: x[1][0], reverse=True)
            for name, update_data in list_subj:
                last_update = update_data[0]
                added = update_data[1]

                r.append('''\
<tr>
  <td><a href="subject/{}">{}</a></td>
  <td class="{}">{}</td>
  <td class="{}">{}</td>
</tr>
'''.format(name.replace(" ", "-").lower(), name, "greyed" if added != last_update else "", added, "greyed" if added == last_update else "", last_update))

            r.append('</tbody></table>\n')

        elif isinstance(information, str):
            if raw:
                r.append('<pre>')
                r.append(information)
                r.append('</pre>')
            else:
                r.append(information)

        else:
            r.append("Information of this type is not handled (Server Error)")


        r.append('\n<hr>\n')

        if footer is not None:
            if isinstance(footer, dict): # indices list
                r.append("Go to: ")
                r.append('<ul>')
                for index, date in footer.items():
                    if index == len(footer) - 1: # the oldest date
                        date = "Oldest"
                    
                    r.append('<li><a href="?%s">Diff %s</a></li>' % (index, date))

                r.append('</ul>\n')
        
        r.append('</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.

        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).

        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.

        """
        try:
            shutil.copyfileobj(source, outputfile)
        except ConnectionAbortedError:
            pass

def main():
    PORT = 8000

    with http.server.ThreadingHTTPServer(("", PORT), Server) as httpd:
        print("serving at port", PORT)
        httpd.serve_forever()

if __name__ == "__main__":
    main()
