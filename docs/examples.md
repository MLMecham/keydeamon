# Examples

The workflow is always the same: **write it in Python, run it, and when you like it, `.save("name")` it** — that writes a TOML into your macros dir, and from then on it's a first-class CLI macro (`keydaemon run name`, `--detach`, `stop`, `list`). Saving again overwrites: your Python script is the source of truth.

```python
import keydaemon

macro = keydaemon.macro().every(60).jitter(5).tap("space").loop()
macro.run()             # try it right now
macro.save("anti_afk")  # → keydaemon run anti_afk, from any terminal, forever
```

---

## Text expansion — a bank of snippets

What makes an expansion different from other macros is the **trigger**: a loop starts on a timer and a hotkey macro starts on one bound key, but an expansion fires when you *type a string* — anywhere, in any app. The trigger text is backspaced away and the replacement typed in its place. Typed triggers are unlimited: they cost zero key bindings, so you can bank as many as you want behind **one** listener:

```python
import keydaemon

(keydaemon.macro()
    .expand("///sig", "Mitchell Mecham | mechamit000@gmail.com")
    .expand("///gg",  "good game, well played!")
    .expand("///brb", "be right back — grabbing food")
    .save("snippets"))
```

```bash
keydaemon run snippets --detach     # now it's a background service
```

```text
Expansions armed: '///sig', '///gg', '///brb'.
Running 'snippets'. Ctrl+C to stop.
```

The saved TOML *is* your snippet list — one readable file, edit it any time:

```toml
[trigger]
type = "expand"

[expansions]
"///sig" = "Mitchell Mecham | mechamit000@gmail.com"
"///gg"  = "good game, well played!"
"///brb" = "be right back — grabbing food"
```

An expansion can also *run actions* instead of typing text — here, typing `///reload` erases itself and taps ++f5++:

```python
keydaemon.macro().tap("f5").wait(0.2).expand("///reload").run().join()
```

!!! tip "Pattern rules"
    Keep patterns lowercase — pressing a modifier key (like ++shift++) mid-pattern resets the match. And no pattern may appear inside any replacement in the bank (typing that replacement would re-trigger forever) — rejected at build time and at load time.

## Autoclicker

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

Prefer to skip the script? It's already built in — `keydaemon run autoclicker` installs and runs the same thing, and [`examples/autoclicker.py`](https://github.com/MLMecham/keydeamon/blob/main/examples/autoclicker.py) is a fully configurable version (button, double-click, rate, keys).

## Minecraft anti-AFK

```python
import keydaemon

(keydaemon.macro()
    .every(270).jitter(30)    # every ~4.5 min, ±30s
    .tap("w").wait(0.1)       # step forward
    .tap("s").wait(0.05)      # step back
    .tap("space")             # jump
    .loop()
    .save("afk"))             # → keydaemon run afk --detach
```

Also built in: `keydaemon run minecraft_afk`.

!!! warning
    Singleplayer / private servers only. Don't take this near anti-cheat.

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
    .save("my_form"))                      # → keydaemon run my_form
```

Don't type coordinates by hand — click through the form once with `keydaemon capture my_form` and the positions are recorded for you.

## Draw a flower

[`examples/flower.py`](https://github.com/MLMecham/keydeamon/blob/main/examples/flower.py) drags the mouse through a rose curve (`r = R·|cos(kθ)|`) in any browser sketch app — petal count, size, and speed are config constants at the top of the file.

```bash
uv run python examples/flower.py
```

## Under the hood: what `.save()` writes

`.save("signature")` produces an ordinary macro TOML — the same format `keydaemon new` scaffolds and the built-in presets install. Edit it by hand, or re-run your Python script to stamp it again:

```toml
[meta]
name = "signature"

[trigger]
type = "expand"
pattern = "///sig"

[behavior]
replace = "Mitchell Mecham | mechamit000@gmail.com"
```

## Compose macros with `.do()`

Macros can reference each other by name — `.do("open_inventory")` runs that saved macro's action sequence inline at that point, and TOML files write the same thing as `"do:open_inventory"`:

```python
import keydaemon

(keydaemon.macro()
    .do("open_inventory")     # runs open_inventory.toml's actions here
    .tap("3").click()
    .do("close_inventory")
    .every(30).loop()
    .save("farm_sequence"))
```

`.do()` stores a **reference, not a copy** — the target's TOML is read fresh on every `.run()`, and `.save()` writes `do:name` into the file. So editing `open_inventory` (by hand or by re-running its script) updates every macro that does it, automatically. Only the target's actions are inlined; its own timing (`every`/`repeat`) is ignored, cycles are rejected, and profiles can't be `do`'d.
