# unquoted

Point it at a YAML file and it tells you which unquoted scalars are not strings —
and which ones three different YAML parsers read three different ways.

You want this if you have YAML that is read by more than one language, or by one
language you did not choose. Kubernetes manifests, Ansible playbooks, CI config,
anything with a Python service and a Go operator looking at the same file.

```console
$ unquoted -e 0644
1:1  split  0644   (value at .)
    pyyaml      int        420
    go-yaml-v3  int        420
    js-yaml     int        644
```

That is a file mode that is `0644` to you, `420` to Python and Go, and `644` to
Node. Nothing raises, nothing warns, and two of those are wrong.

## Install

```
pip install git+https://github.com/committed-nightly/unquoted
```

Python 3.10 or newer. One dependency, PyYAML.

## Use

```
unquoted .                  # every .yml and .yaml below here
unquoted config.yaml        # one file
unquoted -e 012             # one scalar, no file needed
unquoted . --format json    # for something else to read
unquoted . --all            # including the scalars that are fine
```

Exit status is 1 when anything was reported, 0 when nothing was, and 2 when a
file could not be read. There is no `--check` flag because there does not need
to be one:

```yaml
- run: unquoted .
```

## A real example

```console
$ cat release.yml
name: release
on:
  push:
    tags: [v*]
version: 1.10
mode: 0755
retain: 12:30
until: 2026-02-31
enabled: no

$ unquoted release.yml
release.yml:2:1  split  on   (key at on)
    pyyaml      bool       true
    go-yaml-v3  str        on
    js-yaml     str        on

release.yml:5:10  rewritten  1.10   (value at version)
    pyyaml      float      1.1
    go-yaml-v3  float      1.1
    js-yaml     float      1.1

release.yml:6:7  split  0755   (value at mode)
    pyyaml      int        493
    go-yaml-v3  int        493
    js-yaml     int        755

release.yml:7:9  split  12:30   (value at retain)
    pyyaml      int        750
    go-yaml-v3  str        12:30
    js-yaml     str        12:30

release.yml:8:8  split  2026-02-31   (value at until)
    pyyaml      timestamp  <invalid>
    go-yaml-v3  str        2026-02-31
    js-yaml     timestamp  2026-03-03

release.yml:9:10  split  no   (value at enabled)
    pyyaml      bool       false
    go-yaml-v3  str        no
    js-yaml     str        no
```

The last one is the famous one. The interesting ones are the others.

`until: 2026-02-31` is a date that does not exist. go-yaml leaves it a string,
js-yaml silently makes it the 3rd of March, and PyYAML raises `ValueError` —
not `YAMLError`, so `except yaml.YAMLError` around your load will not catch it.

## The verdicts

**`split`** — the implementations disagree, about the type or about the value.
This is the one to fix. `012` is 10 to PyYAML and go-yaml and 12 to js-yaml.

**`retyped`** — they agree it is not a string, and there is no spelling of the
result that gives you your text back. In practice this means dates: you get a
`date`, a `time.Time` or a `Date`, and none of those is what you wrote.

**`rewritten`** — they agree on a number, but the number does not spell the way
you wrote it. `1.10` is the version that becomes 1.1.

Everything else is quiet. **A number that stays a number and reads back
identically is not a finding** — `port: 8080` is an integer everywhere, on the
way out as well as in, and a tool that reports it is just printing your file
back at you. `true` and `null` are quiet for the same reason, and because every
boolean spelling that *does* surprise people — `yes`, `no`, `on`, `off` — comes
out as a split anyway. Use `--all` if you want the quiet ones.

That rule is the difference between 1,776 findings and 8,775 on the same 3,826
files. The 7,000 it drops all said `true` or `false`.

Quoted scalars, explicitly tagged scalars (`!!str 012`), block scalars and
empty values are never reported. Quoting is the fix, so the tool has to be able
to see that you have already applied it.

## What it checks against

`unquoted` does not use the YAML spec as its reference, because on the cases
that matter the implementations do not agree and the spec does not settle it.
Each dialect in `src/unquoted/dialects/` is transcribed from one
implementation's own source, citing the file and function:

| dialect | transcribed from | where you meet it |
| --- | --- | --- |
| `pyyaml` | `yaml/resolver.py`, `yaml/constructor.py` | Python, and SnakeYAML's defaults |
| `go-yaml-v3` | `gopkg.in/yaml.v3` `resolve.go` | Kubernetes, Helm, Docker Compose |
| `js-yaml` | js-yaml 4 `lib/type/*.js` | anything reading YAML in Node |

A transcription is a claim, so `tests/crosscheck/` runs the same 4,836 scalars
through the three parsers for real and compares every tag and every value. The
corpus is half generated — an exhaustive sweep of the characters the resolvers
branch on — and half harvested out of 3,826 YAML files from prometheus,
grafana, home-assistant and ansible. Both halves earned their place: the
generated half caught `1e999`, and the harvested half caught the nanoseconds.

Those tests need Go and Node to run the other two oracles, and skip if they are
not installed. CI has all three.

## Some things that are true

```console
$ unquoted -e 08
1:1  split  08   (value at .)
    pyyaml      str        08
    go-yaml-v3  float      8.0
    js-yaml     int        8
```

Three implementations, three answers, one of which is not even the same kind of
thing.

- `0x_` makes PyYAML raise `ValueError`. Its int pattern accepts a bare
  underscore after `0x`, and the constructor then calls `int("", 16)`.
- `1_000` is 1000, 1000, and the string `1_000`.
- `99999999999999999999` is exact in PyYAML, `1e+20` in go-yaml and
  `100000000000000000000` in js-yaml.
- `2026-9-19` is a date to go-yaml and a string to the other two, because Go
  accepts non-padded month and day fields and their regexes do not.
- `<<` is a merge key to PyYAML and js-yaml and an ordinary string to go-yaml.
- Fractional seconds are kept to nanoseconds by go-yaml, microseconds by PyYAML
  and milliseconds by js-yaml.

## Known limits

The file is scanned with PyYAML's parser, so a document PyYAML's *scanner*
rejects cannot be scanned at all; the tool reports the error and exits 2.
Documents PyYAML *constructs* badly are handled fine, which is the case that
matters.

Only these three implementations. No SnakeYAML, no ruamel, no libyaml in 1.2
mode, and no "the spec says" column — adding one would suggest there is a right
answer to point at, and there is not.

## Licence

MIT.
