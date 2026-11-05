package ai.argus.chartprototype

import org.json.JSONObject
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.abs

data class Sample(val time: LocalDate, val actual: Double?, val projected: Double?, val contribution: Double?)
data class Scenario(val id: String, val titles: Map<String, String>, val currency: String, val shape: String, val points: List<Sample>)
data class Segment(val projected: Boolean, val points: List<Sample>)

fun parseFixtures(json: String): List<Scenario> {
    val root = JSONObject(json)
    require(root.getBoolean("synthetic") && root.getString("date_semantics") == "civil-date-utc")
    val cases = root.getJSONArray("cases")
    return List(cases.length()) { index ->
        val c = cases.getJSONObject(index)
        val title = c.getJSONObject("title")
        val rows = c.getJSONArray("points")
        Scenario(c.getString("id"), mapOf("en" to title.getString("en"), "es-419" to title.getString("es-419")), c.getString("currency"), c.getString("shape"), List(rows.length()) { i ->
            val row = rows.getJSONObject(i)
            fun value(key: String): Double? = if (row.isNull(key)) null else row.getDouble(key)
            Sample(LocalDate.parse(row.getString("time")), value("actual"), value("projected"), value("contribution"))
        })
    }
}

// Every missing row terminates its path; no smoothing, interpolation, or finance math.
fun segments(points: List<Sample>): List<Segment> = listOf(false, true).flatMap { projected ->
    val result = mutableListOf<Segment>()
    var pending = mutableListOf<Sample>()
    fun flush() { if (pending.isNotEmpty()) result += Segment(projected, pending.toList()); pending = mutableListOf() }
    points.forEach { if ((if (projected) it.projected else it.actual) == null) flush() else pending += it }
    flush()
    result
}

fun nearest(points: List<Sample>, fraction: Float): Int? {
    if (points.isEmpty()) return null
    val first = points.first().time.toEpochDay().toDouble()
    val target = first + (points.last().time.toEpochDay() - first) * fraction.coerceIn(0f, 1f)
    return points.indices.minBy { abs(points[it].time.toEpochDay() - target) }
}
fun position(points: List<Sample>, index: Int): Float {
    val first = points.first().time.toEpochDay()
    val range = points.last().time.toEpochDay() - first
    return if (range == 0L) .5f else (points[index].time.toEpochDay() - first).toFloat() / range
}
// Major-currency presentation policy shared by axis ticks and the precise readout.
fun numberFormat(locale: Locale, value: Double): NumberFormat = NumberFormat.getNumberInstance(locale).apply {
    minimumFractionDigits = 2
    maximumFractionDigits = maxOf(2, java.math.BigDecimal.valueOf(value).stripTrailingZeros().scale())
}
fun amount(value: Double?, currency: String, locale: Locale): String =
    value?.let { "$currency " + numberFormat(locale, it).format(it) }
        ?: if (locale.language == "es") "Sin datos" else "No data"
fun date(value: LocalDate, locale: Locale): String = value.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale))

// Decimal midpoint is scale geometry; avoid binary arithmetic inventing tick digits.
fun axisTicks(min: Double, max: Double): List<Double> = listOf(max,
    java.math.BigDecimal.valueOf(min).add(java.math.BigDecimal.valueOf(max))
        .divide(java.math.BigDecimal.valueOf(2)).toDouble(), min)
