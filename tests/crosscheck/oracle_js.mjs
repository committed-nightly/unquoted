// Reads a JSON array of scalar texts on stdin and reports what js-yaml 4 makes
// of each: a tag name and a canonical string, as a JSON array on stdout.
//
// This calls js-yaml's own implicit types in js-yaml's own order rather than
// going through load(), for one reason: load() returns a JavaScript value, and
// JavaScript cannot tell an int from a float. `1.0` resolves to !!float here
// and to the number 1 there, and the tag is half of what is being checked.
import { readFileSync } from 'node:fs'
import yaml from 'js-yaml'

const IMPLICIT = yaml.DEFAULT_SCHEMA.compiledImplicit
const SHORT = tag => tag.replace('tag:yaml.org,2002:', '')

function canonical (tag, value) {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (value instanceof Date) return value.toISOString().replace(/\.000Z$/, 'Z')
  if (typeof value === 'number') {
    if (Number.isNaN(value)) return 'nan'
    if (value === Infinity) return 'inf'
    if (value === -Infinity) return '-inf'
    if (tag === 'int') return BigInt(value).toString()
    // String(-0) is "0", which would hide a sign the parser did produce.
    if (Object.is(value, -0)) return '-0.0'
    return String(value)
  }
  return String(value)
}

function describe (text) {
  for (const type of IMPLICIT) {
    if (type.kind !== 'scalar') continue
    if (!type.resolve(text)) continue
    const tag = SHORT(type.tag)
    // A type with no construct (merge) leaves the scalar as it was written.
    if (typeof type.construct !== 'function') return [tag, text]
    return [tag, canonical(tag, type.construct(text))]
  }
  return ['str', text]
}

const texts = JSON.parse(readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify(texts.map(describe)))
