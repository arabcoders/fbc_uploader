package main

import (
	"fmt"
	"strconv"
	"strings"
)

var sizeMultipliers = map[string]float64{
	"b":   1,
	"k":   1024,
	"kb":  1024,
	"ki":  1024,
	"kib": 1024,
	"m":   1024 * 1024,
	"mb":  1024 * 1024,
	"mi":  1024 * 1024,
	"mib": 1024 * 1024,
	"g":   1024 * 1024 * 1024,
	"gb":  1024 * 1024 * 1024,
	"gi":  1024 * 1024 * 1024,
	"gib": 1024 * 1024 * 1024,
	"t":   1024 * 1024 * 1024 * 1024,
	"tb":  1024 * 1024 * 1024 * 1024,
	"ti":  1024 * 1024 * 1024 * 1024,
	"tib": 1024 * 1024 * 1024 * 1024,
}

func parseByteSize(raw string) (int64, error) {
	value := strings.TrimSpace(strings.ToLower(raw))
	if value == "" {
		return 0, fmt.Errorf("size cannot be empty")
	}

	split := len(value)
	for idx, r := range value {
		if (r < '0' || r > '9') && r != '.' {
			split = idx
			break
		}
	}

	numberPart := strings.TrimSpace(value[:split])
	if numberPart == "" {
		return 0, fmt.Errorf("invalid size %q", raw)
	}

	number, err := strconv.ParseFloat(numberPart, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid size %q: %w", raw, err)
	}
	if number <= 0 {
		return 0, fmt.Errorf("size must be greater than zero")
	}

	unit := strings.TrimSpace(value[split:])
	if unit == "" {
		if strings.Contains(numberPart, ".") {
			return 0, fmt.Errorf("fractional byte sizes require a unit")
		}

		intValue, err := strconv.ParseInt(numberPart, 10, 64)
		if err != nil {
			return 0, fmt.Errorf("invalid size %q: %w", raw, err)
		}

		return intValue, nil
	}

	multiplier, ok := sizeMultipliers[unit]
	if !ok {
		return 0, fmt.Errorf("unknown size suffix %q", unit)
	}

	return int64(number * multiplier), nil
}
