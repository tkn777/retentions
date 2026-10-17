# Roadmap

## 1.4

### Inline retention intervalls

Support arbitrary calendar interval widths for `hours`, `days`, `weeks`, and `months`, such as `--days2`, `--days3`, or `--weeks3`. The suffix specifies the bucket width; the argument specifies how many occupied buckets to retain, keeping the newest item in each bucket.

Group whole calendar units backwards from the unit containing program start, using ISO weeks for weekly intervals. For example, `--days2` groups today with yesterday, then the preceding two days, and so on.

Apply retention stages hierarchically from smaller to larger interval widths, independently of CLI argument order. For example, `--days7` is processed before `--weeks`, followed by `--days8`. For sorting only, treat one month as 30 days, matching the month conversion used by the existing `--max-age` filter. Monthly buckets remain calendar-based.

Keep existing options and retain the single Python script without additional runtime dependencies.
