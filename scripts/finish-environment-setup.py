# Complete the setup of the gnuradio environment for the COVID-19 spectrum monitoring project

import os, sys, subprocess, importlib, ctypes, shutil
import traceback as tb
from collections import OrderedDict

# config
SCRIPT_PATH = os.path.abspath(__file__)
PROJECT_PATH = os.path.abspath('..')

POTHOS_PATH = r'C:\program files\pothossdr\bin'

#### Project build parameters
# each key is the import name; value is the name pip needs to install
PYTHON_EXE = r'C:\python27\python.exe'

PROJECT_IMPORTS = dict(yaml='pyyaml', pandas='pandas', psutil='psutil')

COPIES = [('bladerf.conf', '..'),
          ('bladerf.conf', POTHOS_PATH)]

HIER_BLOCKS = (
    os.path.join(PROJECT_PATH, 'grc', 'blocks', 'bladerf_source.grc'),
    os.path.join(PROJECT_PATH, 'grc', 'blocks', 'energy_detection.grc'),
    os.path.join(PROJECT_PATH, 'grc', 'blocks', 'energy_detection_file_sink.grc'),
)

FLOWGRAPHS = (
    os.path.join(PROJECT_PATH, 'grc', 'calibrate_noise.grc'),
    os.path.join(PROJECT_PATH, 'grc', 'swept_power_to_disk.grc'),
)

# First, perform copies
if __name__ == '__main__':
    
    if ctypes.windll.shell32.IsUserAnAdmin():
        print('Copying config files')

        try:
            for src, dest in COPIES:
                shutil.copy(src, dest)
        except:
            tb.print_exc()
            print('FAILED')
            raw_input('press enter to close')
            sys.exit(1)
    else:
        print('Restarting as administrator')
        # Re-run the program with admin rights
        try:
            os.chdir(os.path.split(os.path.abspath(__file__))[0])
            ctypes.windll.shell32.ShellExecuteW(None, u"runas", unicode(sys.executable), unicode(" ".join(sys.argv)), None, 1)
        except:
            tb.print_exc()
            print('failed to respawn as administrator')
            raw_input('press enter to close')
        finally:
            sys.exit(0)

### pothos environment
print(PROJECT_PATH)
sys.path.insert(1,POTHOS_PATH) # import from above directory
os.chdir(POTHOS_PATH)
import GNURadioHelper as helper
helper.Environment.SendMessage = ctypes.windll.user32.SendNotifyMessageW

def setter(env, name, value):
	ret = helper.Environment._set(env, name, value)
	os.environ[name] = value
	return ret
helper.Environment._set, helper.Environment.set = helper.Environment.set, setter


helper.__file__ = os.path.join(POTHOS_PATH, 'GNURadioHelper.py')

# monkeypatch GNURadioHelper to rely less on user intervention
CHECKS = OrderedDict([(tup[0], tup[1:]) for tup in helper.CHECKS])

def pip_install(*args):
    ''' get exceptions instead of printing on pip_install failures
    '''
    ret = subprocess.call([helper.PIP_EXE, 'install']+list(args), shell=True)
    if ret != 0:
        raise RuntimeError("pip failed to install %s"%str(list(args)))
helper.pip_install = pip_install

# add checks and handler to install project extras
def check_import_extras():
    for name in PROJECT_IMPORTS.keys():
        importlib.import_module(name)

def handle_import_extras():
    pip_install(*list(PROJECT_IMPORTS.values()))
CHECKS['PROJECT_EXTRAS'] = ('project extra modules', check_import_extras, handle_import_extras)

def installs(max_passes=3):
    global fix_pass

    for fix_pass in range(fix_pass, max_passes+1):
        for key, check in dict(CHECKS).items():
            what, check, handle = check
            try:
                msg = check()
                
            except Exception as ex:
                print(" - FIXING '%s' on exception '%s'" % (what, str(ex)))

                try:
                    handle()
                except:                    
                    tb.print_exc()
                    print("- FAILED '%s' fix (attempt %i/%i)"%(what, fix_pass+1, max_passes))
                    continue
            else:
                print(" - PASS %s" % what)
                del CHECKS[key]
            
            # msgs[key] = msg
            # statuses[key] = checkPassed

        if len(CHECKS) == 0:
            print('python and library environments passed all checks!\n')
            break
    else:
        names = tuple([check[0] for key, check in CHECKS.items()])
        raise Exception("failed to fix %s in %i attempts"%(names, max_passes))


if __name__ == '__main__':
    try:
        try:
            if len(sys.argv) == 3:
                fix_pass = int(sys.argv[2])
            else:
                fix_pass = 0
        except:
            ValueError("expected int argument in second position, got %s"%repr(sys.argv[2]))

        print '******', helper.guess_bin_path()
        print('Checking python and library installs')

        installs()
    except:
        tb.print_exc()
        print('FAILED')
        print('press enter to close')
        raw_input('press enter to close')
        sys.exit(1)

# now on to build the GRC files
import warnings
warnings.simplefilter('ignore')

from gnuradio import gr
try:
    from grc.core.Platform import Platform
except ImportError:
    from gnuradio.grc.core.Platform import Platform

class GRCC:
    def __init__(self):
        self.platform = Platform(
            prefs_file=gr.prefs(),
            version=gr.version(),
            version_parts=(gr.major_version(), gr.api_version(), gr.minor_version())
        )

    def build(self, grcfile, out_dir=None):
        if out_dir is None:
            home = os.environ.get("HOME", os.environ.get('USERPROFILE'))
            out_dir = os.path.join(home, '.grc_gnuradio')
        out_dir = os.path.join(out_dir, '')

        print(' - BUILD %s' % grcfile)
        print('    -> %s'%out_dir)
        # return 

        fg = self.platform.get_new_flow_graph()
        fg.import_data(self.platform.parse_flow_graph(grcfile))
        fg.grc_file_path = os.path.abspath(grcfile)
        fg.validate()

        if not fg.is_valid():
            raise StandardError("\n\n".join(
                ["Validation failed:"] + fg.get_error_messages()
            ))

        gen = self.platform.Generator(fg, out_dir)
        gen.write()

if __name__ == '__main__':
    try:
        print('Building .grc -> .py')
        
        grcc = GRCC()
        for path in HIER_BLOCKS:
            grcc.build(path)

        grcc = GRCC()
        for path in FLOWGRAPHS:        
            grcc.build(path, out_dir=os.path.join(PROJECT_PATH, 'grc'))
    except:
        tb.print_exc()
        print('FAILED')
        raw_input('press enter to close')
        sys.exit(1)

    print('SUCCESS!')