import os
import threading
import collections
import time

import sublime

from . import scanners


class FileSearcherThread(threading.Thread):
    """
    Search directories recursively in separate thread and push results onto a
    queue.
    """
    def __init__(self, matching_files, target_string, result_queue):
        super().__init__()
        self._stop_thread = threading.Event()
        self._matching_files = matching_files
        self._search_terms = [x.lower() for x in target_string.split()]

        self._result_queue = result_queue
        self._files_searched = 0
        self._files_searched_last_update = 0

        settings = sublime.load_settings('FindInProject.sublime-settings')
        self.max_line_len = settings.get('find_in_project_max_line_len', 100)

        self.scanner = scanners.FileScanner(settings)

    def stop(self):
        """
        Stop the thread after it is done searching the current file.
        """
        self._stop_thread.set()

    def run(self):
        """
        Override the run method from threading.Thread to do a search when the
        thread is started. This should not be called directly obviously.
        """
        for filepath in self._matching_files:
            if self._stop_requested():
                return

            result = self._search_file(filepath)
            self._files_searched = self._files_searched + 1

            if len(result):
                ret = {"filepath": filepath, "result": result, "files_searched": self._files_searched}
                self._result_queue.put(ret)
                self._files_searched_last_update = time.time()
            elif time.time() > (self._files_searched_last_update + 0.2):
                update = {"files_searched": self._files_searched}
                self._result_queue.put(update)
                self._files_searched_last_update = time.time()


        # Send a final update on files searched
        update = {"files_searched": self._files_searched}
        self._result_queue.put(update)

        # Wait until all results have been read from the queue - then terminate
        self._result_queue.join()

    def _stop_requested(self):
        """
        Check if stop has been requested.
        """
        flag = self._stop_thread.wait(0)
        return flag

    def _search_file(self, path):
        """Search a file for the search terms."""

        ret = collections.OrderedDict()
        for line_num, line_content in self.scanner.read_lines(path):
            # Search line for target string
            loc = self._line_matches(line_content, self._search_terms)
            if loc >= 0:
                if len(line_content) > self.max_line_len:
                    line_content = self._limit_line(line_content, loc)
                ret[line_num] = line_content

        if self.scanner.warnings:
            ret[0] = self.scanner.warnings[0]

        return ret

    def _line_matches(self, line, terms):
        lower_line = line.lower()
        for term in terms:
            location = lower_line.find(term)
            if location >= 0:
                return location

        return -1

    def _limit_line(self, line, loc):
        """
        Limit the provided line according to the settings.
        """
        single_side_len = int(self.max_line_len/2)

        start = loc - single_side_len
        if start < 0:
            start = 0

        end = loc + single_side_len
        if (end >= len(line)):
            end = len(line)-1

        limited_line = ""
        if start != 0:
            limited_line = limited_line + "[…]"

        limited_line = limited_line + line[start:end]
        if end != len(line)-1:
            limited_line = limited_line + "[…]"

        return limited_line
