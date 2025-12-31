1. Did not tell me clearly that I needed tmux
➜  testing git:(main) ✗ scope setup
Traceback (most recent call last):
  File "/Users/ada/.local/bin/scope", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1485, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1406, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1873, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1269, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 824, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/scope/commands/setup.py", line 35, in setup
    if not tmux_is_installed():
           ^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/scope/core/tmux.py", line 54, in is_installed
    result = subprocess.run(
             ^^^^^^^^^^^^^^^
  File "/Users/ada/.pyenv/versions/3.12.12/lib/python3.12/subprocess.py", line 548, in run
    with Popen(*popenargs, **kwargs) as process:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.pyenv/versions/3.12.12/lib/python3.12/subprocess.py", line 1026, in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
  File "/Users/ada/.pyenv/versions/3.12.12/lib/python3.12/subprocess.py", line 1955, in _execute_child
    raise child_exception_type(errno_num, err_msg, err_filename)
FileNotFoundError: [Errno 2] No such file or directory: 'tmux'

2. scope --version is broken
➜  testing git:(main) ✗ uv tool install scopeai
Resolved 16 packages in 251ms
Audited 16 packages in 0.47ms
Installed 2 executables: scope, scope-hook
➜  testing git:(main) ✗ scope --version
Traceback (most recent call last):
  File "/Users/ada/.local/bin/scope", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1485, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1405, in main
    with self.make_context(prog_name, args, **extra) as ctx:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1216, in make_context
    self.parse_args(ctx, args)
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1829, in parse_args
    rest = super().parse_args(ctx, args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 1227, in parse_args
    _, args = param.handle_parse_result(ctx, opts, args)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 2578, in handle_parse_result
    value = self.process_value(ctx, value)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 3313, in process_value
    return super().process_value(ctx, value)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/core.py", line 2448, in process_value
    value = self.callback(ctx, self, value)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/ada/.local/share/uv/tools/scopeai/lib/python3.12/site-packages/click/decorators.py", line 500, in callback
    raise RuntimeError(
RuntimeError: 'scope' is not installed. Try passing 'package_name' instead.

3. I closed the subagent id=3 using ctrl+c but it didnt automatically get closed in the dashboard
  Expected closing a claude process aborts it.

4. quitting with q should have a confirmation message. Even better would be to use ctrl+c as a non-native of terminals
  also quitting should also terminate all windows and mark them as exited.

5. Remove scope top, `scope` and `scope top` are the same and add confusion

6. The view doesn’t tell me which folder/repo i am in.
    Maybe add it to the status bar from tmux at the bottom

7. I spawned a new sub-agent but the left side still highlights id=6. This was confusing. Track correct session highlight.

8. When I click on the agents to switch between them, I expect the key focus to keep staying here. But it actually moves to the claude input box.

      What I mean
      1. I click on agent 6.
      2. ⁠I expect to use arrow keys to switch between 6, 6.0, and 7

    Clicking should open the claude code window but keep the focus on TUI.

9. Even after being done, I think it might be useful for the activity column to show what the last status is.
