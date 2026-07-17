# Examples

Real recipes, shortest first. Python versions use the fluent builder; most have a TOML twin you can drop in your macros dir.

## Autoclicker

=== "CLI (built-in preset)"

    ```bash
    keydaemon run autoclicker
    # F6 toggles clicking, F8 quits.
    # First run installs autoclicker.toml — edit it to change keys or speed.
    ```

=== "Python"

    ```python
    import keydaemon

    keydaemon.preset("autoclicker").run().join()
    ```

=== "From scratch"

    ```python
    import keydaemon

    (keydaemon.macro()
        .times_per_second(4)      # rate in Hz — sugar for .every(0.25)
        .jitter(0.06)             # human-ish wobble
        .click("left")
        .loop()
        .hotkey("f6")             # press to start, press again to stop
        .exit_key("f8")           # press to quit entirely
        .run()
        .join())
    ```

A fully configurable script (button, double-click, rate, keys) lives at [`examples/autoclicker.py`](https://github.com/MLMecham/keydeamon/blob/main/examples/autoclicker.py).

## Minecraft anti-AFK

=== "CLI"

    ```bash
    keydaemon run minecraft_afk --detach     # runs in the background
    keydaemon stop minecraft_afk             # when you're done
    ```

=== "Python"

    ```python
    import keydaemon

    keydaemon.preset("minecraft_afk").run()
    # steps forward, back, and jumps every ~4.5 min (±30s)
    ```

!!! warning
    Singleplayer / private servers only. Don't take this near anti-cheat.

## Text expansion

Type `///sig` anywhere and it becomes your signature:

```toml
[trigger]
type = "expand"
pattern = "///sig"

[behavior]
replace = "Mitchell Mecham | mechamit000@gmail.com"
```

## Hold a key while a condition is met

```python
import keydaemon

# Sprint until the stamina pixel goes red, then let go and stop everything.
(keydaemon.macro()
    .press("shift")
    .wait_for_color(120, 980, "#C0392B")   # blocks until pixel matches
    .release("shift")
    .kill_all()                            # bail out of ALL automation
    .run())
```

`.kill_all()` (TOML: `stop:all`) is the sanctioned macro-side version of the emergency kill — see [Safety](safety.md).

## Form filler

```python
import keydaemon

(keydaemon.macro()
    .move_to(430, 312).click().type("Mitchell")
    .tap("tab").type("Mecham")
    .tap("tab").type("mechamit000@gmail.com")
    .move_to(510, 640).click()             # submit
    .run())
```

Record the coordinates by clicking through the form once with `keydaemon capture my_form`.

## Draw a flower

[`examples/flower.py`](https://github.com/MLMecham/keydeamon/blob/main/examples/flower.py) drags the mouse through a rose curve (`r = R·|cos(kθ)|`) in any browser sketch app — petal count, size, and speed are config constants at the top of the file.

```bash
uv run python examples/flower.py
```

## Compose macros with `do`

```toml
# farm_sequence.toml — reuses open_inventory.toml inline
[trigger]
type = "loop"

[behavior]
every = 10
jitter = 2

[actions]
sequence = [
    "do:open_inventory",    # flattened at load time, cycles rejected
    "tap:e",
    "do:close_inventory",
]
```
