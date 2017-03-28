import time
import queue
import threading

import sublime_plugin
import sublime

from . import filesearcher
from . import resultbuffer


class FindInProject(sublime_plugin.TextCommand):
   """
   Find In Project - a Sublime Text 3 plugin for text search in projects. The
   search is performed in a background thread and results are presented in an
   interactive view.
   """
   def __init__(self, view):
      sublime_plugin.TextCommand.__init__(self, view)
      self.result_queue = None
      self.result_buffer = None,
      self.search_thread = None
      self.status_string_idx = 0;
      self.num_hits = 0
      self.num_file_hits = 0
      self.last_status_update = 0
      self.search_cancelled = False

      settings = sublime.load_settings('FindInProject.sublime-settings')
      self.excessive_hits_count = settings.get('find_in_project_excessive_hits_count', 5000)

   def run(self, edit):
      """
      Show input panel to get target string for search
      """
      win = sublime.active_window()
      view = win.active_view()

      # See if we can find a selection to use as initial guess for target string
      initial_input_text = ""
      for region in view.sel():
            if not region.empty():
                # Get selected text
                txt = view.substr(region)
                if "\n" not in txt:
                  initial_input_text = txt
                  break

      # Present user input panel
      win.show_input_panel("Find in project:", initial_input_text, self.input_panel_on_done, None, None)

   def input_panel_on_done(self, user_input):
      """
      Callback for input panel on done. Search files in project for the provided
      string.
      """
      if len(user_input) == 0:
         return

      # Get active window and view
      win = sublime.active_window()
      view = win.active_view()

      # Get project data
      project_data = win.project_data()
      if ("folders" not in project_data) or len(project_data["folders"]) == 0:
         return

      # Reset member vars for new search
      self.result_queue = queue.Queue()
      self.status_string_idx = 0;
      self.num_hits = 0
      self.num_file_hits = 0
      self.last_status_update = 0
      self.search_cancelled = False

      # Search all project dirs
      project_dirs = []
      for folder in project_data["folders"]:
         project_dirs.append(folder["path"])

      # Initialize result buffer/view
      self.result_buffer = resultbuffer.ResultBuffer(win, user_input)

      # Start search thread
      self.search_thread = filesearcher.FileSearcherThread(project_dirs, user_input, self.result_queue)
      self.search_thread.start()

      # Come back in 1 ms to start handling results on an alternate thread
      sublime.set_timeout_async(self.handle_search_results, 1)

   def handle_search_results(self):
      """
      Handle search results that search thread places on the result queue
      """
      while True:
         self.update_status()

         # Check if result buffer has been closed - in this case we cancel the
         # search.
         if (self.search_cancelled == False) and (self.result_buffer.is_closed()):
            self.search_thread.stop()
            self.search_cancelled = True

         # If there are any results
         if not self.result_queue.empty():
            result = self.result_queue.get()

            # Update number of hits but ensure it does not include warning/error
            # strings
            if len(result["result"]):
               if 0 not in result["result"]:
                  self.num_hits = self.num_hits + len(result["result"])
                  self.num_file_hits = self.num_file_hits + 1

            # If we reach excessive limit start dropping results and stop search
            if (self.excessive_hits_count != 0) and (self.num_hits > self.excessive_hits_count):
               self.search_thread.stop()
               self.search_cancelled = True

            # Update result view
            if not self.search_cancelled:
               self.result_buffer.insert_result(result)
            self.result_queue.task_done()

         # Are we done ?
         if (self.search_thread.isAlive() == False) and (self.result_queue.empty() == True):
            self.set_final_status()
            break

   def update_status(self):
      """
      Update text in status bar
      """
      if time.time() > (self.last_status_update + 0.2):
         self.last_status_update = time.time()
         win = sublime.active_window()
         self.status_string_idx = self.status_string_idx + 1

         if self.status_string_idx == 0:
            win.status_message("FindInProject: Searching in project | [%i hits across %i files so far]" % (self.num_hits, self.num_file_hits))
         elif self.status_string_idx == 1:
            win.status_message("FindInProject: Searching in project / [%i hits across %i files so far]" % (self.num_hits, self.num_file_hits))
         elif self.status_string_idx == 2:
            win.status_message("FindInProject: Searching in project - [%i hits across %i files so far]" % (self.num_hits, self.num_file_hits))
         elif self.status_string_idx > 2:
            win.status_message("FindInProject: Searching in project \ [%i hits across %i files so far]" % (self.num_hits, self.num_file_hits))
            self.status_string_idx = 0

   def set_final_status(self):
      """
      Set final text in status bar
      """
      win = sublime.active_window()
      if self.search_cancelled:
         win.status_message("FindInProject: Search cancelled (due to close or excessive number of hits)")
      else:
         win.status_message("FindInProject: Search done [%i hits across %i files]" % (self.num_hits, self.num_file_hits))