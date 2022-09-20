#!C:\Python27\python.exe
"""
Copyright 2016 Free Software Foundation, Inc.
This file is part of GNU Radio

GNU Radio Companion is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

GNU Radio Companion is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
"""

import os
import time
import sys
import warnings


GR_IMPORT_ERROR_MESSAGE = """\
Cannot import gnuradio.

Is the model path environment variable set correctly?
    All OS: PYTHONPATH

Is the library path environment variable set correctly?
    Linux: LD_LIBRARY_PATH
    Windows: PATH
    MacOSX: DYLD_LIBRARY_PATH
"""


def die(error, message):
    msg = "{0}\n\n({1})".format(message, error)
    try:
        import gtk
        d = gtk.MessageDialog(
            type=gtk.MESSAGE_ERROR,
            buttons=gtk.BUTTONS_CLOSE,
            message_format=msg,
        )
        d.set_title(type(error).__name__)
        d.run()
        exit(1)
    except ImportError:
        exit(type(error).__name__ + '\n\n' + msg)


def check_gtk():
    try:
        warnings.filterwarnings("error")
        import pygtk
        pygtk.require('2.0')
        import gtk
        gtk.init_check()
        warnings.filterwarnings("always")
    except Exception as err:
        die(err, "Failed to initialize GTK. If you are running over ssh, "
                 "did you enable X forwarding and start ssh with -X?")


def check_gnuradio_import():
    try:
        from gnuradio import gr
    except ImportError as err:
        die(err, GR_IMPORT_ERROR_MESSAGE)


def check_blocks_path():
    if 'GR_DONT_LOAD_PREFS' in os.environ and not os.environ.get('GRC_BLOCKS_PATH', ''):
        die(EnvironmentError("No block definitions available"),
            "Can't find block definitions. Use config.conf or GRC_BLOCKS_PATH.")


def run_main():
    script_path = os.path.dirname(os.path.abspath(__file__))
    source_tree_subpath = "/grc/scripts"

    if not script_path.endswith(source_tree_subpath):
        # run the installed version
        from gnuradio.grc.main import main
    else:
        print("Running from source tree")
        sys.path.insert(1, script_path[:-len(source_tree_subpath)])
        from grc.main import main
    exit(main())


if __name__ == '__main__':
    name = 'calibrate_noise'

    try:
        # munge current directory
        project_path = os.path.join(os.path.abspath(os.curdir))
        sys.path.insert(1,os.path.join(project_path,'grc'))
        os.chdir(r'C:\Program Files\PothosSDR\bin')

        os.environ['PATH'] += ';C:\\Python27\\lib\\site-packages\\numpy\\core;C:\\Program Files\\PothosSDR\\bin;C:\\Program Files\\GTK2-Runtime Win64\\bin;C:\\Program Files\\GTK2-Runtime Win64\\bin;'

        # prechecks borrowed from C:\\Program Files\\PothosSDR\\bin\\gnuradio_companion.py
        check_gnuradio_import()
        check_gtk()
        check_blocks_path()

        script_path = os.path.join(project_path, 'grc', name+'.py')
        sys.argv = [script_path]

        with open(script_path, 'rb') as f:
            exec(f)

        sys.exitfunc()

        ## Alternative: a loop
        # while True:
        #     try:
        #         with open(script_path, 'rb') as f:
        #             exec(f)
        #     except KeyboardInterrupt as e:
        #         exit()
        #     except Exception as e:
        #         with open(os.path.join(project_path, 'grc/exceptions.txt', 'wb+')) as w:
        #             print str(e)
        #             w.write(str(e))
    finally:
        raw_input('finished; press enter to close')


    
    
    # flowgraph = __import__('grc.' + name)

    # os.chdir(r'C:\Program Files\PothosSDR\bin')
    # flowgraph.main()

    # while True:
    #     try:
    #         flowgraph.main()
    #     except KeyboardInterrupt as e:
    #         exit()
    #     except Exception as e:
    #         with open(os.path.join(project_path, 'grc/exceptions.txt', 'wb+')) as w:
    #             print str(e)
    #             w.write(str(e))