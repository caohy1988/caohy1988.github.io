"""Written by okf_bq_graph.receipt_window. Deliberately `usercustomize`, not `sitecustomize`: this
interpreter already ships a `sitecustomize` that completes sys.path, and a PYTHONPATH copy shadows it. Importing the
bridge has no effect on its own; the guards are installed here, at interpreter start-up, before the SDK example runs."""
import okf_window_bridge as _bridge

_bridge.install()
