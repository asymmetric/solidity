#!/usr/bin/env python3

from argparse import ArgumentParser
import sys
import os
import subprocess
import re
import glob
import threading
import time

DESCRIPTION = """Regressor is a tool to run regression tests in a CI env."""

class PrintDotsThread(object):
    """Prints a dot every "interval" (default is 300) seconds"""

    def __init__(self, interval=300):
        self.interval = interval

        thread = threading.Thread(target=self.run, args=())
        thread.daemon = True
        thread.start()

    def run(self):
        """ Runs until the main Python thread exits. """
        ## Print a newline at the very beginning.
        print("")
        while True:
            # Print dot
            print(".")
            time.sleep(self.interval)

class regressor():
    _re_sanitizer_log = re.compile(r"""ERROR: (?P<sanitizer>\w+).*""")
    _error_blacklist = ["AddressSanitizer", "libFuzzer"]

    def __init__(self, description, args):
        self._description = description
        self._args = self.parseCmdLine(description, args)
        self._repo_root = os.path.dirname(sys.path[0])
        self._fuzzer_path = os.path.join(self._repo_root,
                                         "build/test/tools/ossfuzz")
        self._logpath = os.path.join(self._repo_root, "test_results")

    def parseCmdLine(self, description, args):
        argParser = ArgumentParser(description)
        argParser.add_argument('-o', '--out-dir', required=True, type=str,
                       help="""Directory where test results will be written""")
        return argParser.parse_args(args)

    """
        Runs command in bash shell logging stdout/err to logfile and
        returning exit status (0-255) of the command.
        Exit status:
            0       -> Success
            1-255   -> Failure
    """
    @staticmethod
    def run_cmd(command, logfile=None, env=None):
        if not logfile:
            logfile = os.devnull

        if not env:
            env = os.environ.copy()

        logfh = open(logfile, 'w')
        proc = subprocess.Popen(command, shell=True, executable='/bin/bash',
                                env=env, stdout=logfh,
                                stderr=subprocess.STDOUT)
        ret = proc.wait()
        logfh.close()
        return ret

    def process_log(self, logfile):
        ## Log may contain non ASCII characters, so we simply stringify them
        ## since they don't matter for regular expression matching
        rawtext = str(open(logfile, 'rb').read())
        list = re.findall(self._re_sanitizer_log, rawtext)
        numSuppressedLeaks = list.count("LeakSanitizer")
        rv = any(word in list for word in self._error_blacklist)
        return not rv, numSuppressedLeaks

    def run(self):
        testStatus = []
        for fuzzer in glob.iglob("{}/*_ossfuzz".format(self._fuzzer_path)):
            basename = os.path.basename(fuzzer)
            logfile = os.path.join(self._logpath, "{}.log".format(basename))
            corpus_dir = "/tmp/solidity-fuzzing-corpus/{0}_seed_corpus" \
                .format(basename)
            cmd = "find {0} -type f | xargs -n1 {1}".format(corpus_dir, fuzzer)
            cmd_status = self.run_cmd(cmd, logfile=logfile)
            if cmd_status:
                ret, numLeaks = self.process_log(logfile)
                if not ret:
                    print(
                        "\t[-] libFuzzer reported failure for {0}. "
                        "Failure logged to test_results".format(
                            basename))
                    testStatus.append(cmd_status)
                else:
                    print("\t[+] {0} passed regression tests but leaked "
                          "memory.".format(basename))
                    print("\t\t[+] Suppressed {0} memory leak reports".format(
                            numLeaks))
                    testStatus.append(0)
            else:
                print("\t[+] {0} passed regression tests.".format(basename))
                testStatus.append(cmd_status)
        return any(testStatus)


if __name__ == '__main__':
    dotprinter = PrintDotsThread()
    tool = regressor(DESCRIPTION, sys.argv[1:])
    sys.exit(tool.run())
