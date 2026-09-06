"""Assemble evidence/report.md = prose head + generated tables + prose tail."""
import subprocess, sys
subprocess.run([sys.executable, "-m", "okf_bq_graph.report"], check=True)
head = open("evidence/report_prose_head.md").read()
tables = open("evidence/report_tables.md").read()
tail = open("evidence/report_prose_tail.md").read()
open("evidence/report.md", "w").write(head.rstrip() + "\n\n# Measured tables (generated from evidence JSON)\n\n" + tables.rstrip() + "\n\n" + tail)
print("evidence/report.md assembled:", len(open("evidence/report.md").read()), "chars")
