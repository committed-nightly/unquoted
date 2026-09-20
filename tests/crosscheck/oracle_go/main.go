// Reads a YAML mapping on stdin and reports what gopkg.in/yaml.v3 made of each
// plain scalar value: a tag name and a canonical string, as JSON on stdout.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"strconv"
	"time"

	"gopkg.in/yaml.v3"
)

func describe(v interface{}) [2]string {
	switch value := v.(type) {
	case nil:
		return [2]string{"null", "null"}
	case bool:
		if value {
			return [2]string{"bool", "true"}
		}
		return [2]string{"bool", "false"}
	case int:
		return [2]string{"int", strconv.FormatInt(int64(value), 10)}
	case int64:
		return [2]string{"int", strconv.FormatInt(value, 10)}
	case uint64:
		return [2]string{"int", strconv.FormatUint(value, 10)}
	case float64:
		if math.IsNaN(value) {
			return [2]string{"float", "nan"}
		}
		if math.IsInf(value, 1) {
			return [2]string{"float", "inf"}
		}
		if math.IsInf(value, -1) {
			return [2]string{"float", "-inf"}
		}
		// -1 precision gives the shortest string that parses back to the same
		// float64, so Python's float() reads exactly this number and the two
		// sides are compared on the value rather than on two formatters.
		return [2]string{"float", strconv.FormatFloat(value, 'g', -1, 64)}
	case time.Time:
		utc := value.UTC()
		layout := "2006-01-02T15:04:05"
		out := utc.Format(layout)
		if utc.Nanosecond() != 0 {
			out = utc.Format("2006-01-02T15:04:05.999999999")
		}
		return [2]string{"timestamp", out + "Z"}
	case string:
		return [2]string{"str", value}
	}
	return [2]string{"unknown", fmt.Sprintf("%v", v)}
}

func main() {
	source, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var generic map[string]interface{}
	if err := yaml.Unmarshal(source, &generic); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out := map[string][2]string{}
	for key, value := range generic {
		out[key] = describe(value)
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
