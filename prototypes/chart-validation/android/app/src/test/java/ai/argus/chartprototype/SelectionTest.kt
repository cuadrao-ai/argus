package ai.argus.chartprototype
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.util.Locale

class SelectionTest {
    private val first = LocalDate.of(2026, 1, 2)
    @Test fun axisAndReadoutPreserveCanonicalFixtureCents() {
        val cases = javaClass.classLoader!!.getResourceAsStream("series.json")!!.bufferedReader().use { parseFixtures(it.readText()) }
        for (locale in listOf(Locale.US, Locale.forLanguageTag("es-419"))) {
            val oddCent = cases.flatMap { it.points }.flatMap { listOfNotNull(it.actual, it.projected) }
                .first { java.math.BigDecimal.valueOf(it).movePointRight(2).toBigInteger().abs().testBit(0) }
            val midpoint = axisTicks(0.0, oddCent)[1]
            val expected = java.math.BigDecimal.valueOf(oddCent).divide(java.math.BigDecimal.valueOf(2))
            val shownMidpoint = numberFormat(locale, midpoint).format(midpoint)
            assertEquals(expected.toDouble(), numberFormat(locale, midpoint).parse(shownMidpoint)!!.toDouble(), 0.000000001)
            for (case in cases) {
                for (value in case.points.flatMap { listOfNotNull(it.actual, it.projected, it.contribution) }) {
                    val displayed = numberFormat(locale, value).format(value)
                    assertEquals(value, numberFormat(locale, value).parse(displayed)!!.toDouble(), 0.000001)
                    assertEquals("${case.currency} $displayed", amount(value, case.currency, locale))
                }
            }
        }
    }
    @Test fun datesUseElapsedDaysNotRowIndexAndTiesChooseEarlier() {
        val points = listOf(0L, 2L, 10L).map { Sample(first.plusDays(it), 10.0, null, null) }
        assertEquals(1, nearest(points, .5f))
        assertEquals(0, nearest(points.take(2), .5f))
        assertEquals(0, nearest(points, -1f))
        assertEquals(2, nearest(points, 2f))
        assertNull(nearest(emptyList(), .5f))
        assertEquals(0, nearest(points.take(1), 1f))
    }
    @Test fun nullTerminatesEachSeriesIndependently() {
        val rows = listOf(Sample(first, -10.0, null, null), Sample(first.plusDays(1), null, 2.0, null), Sample(first.plusDays(2), 20.0, 3.0, 10.0))
        assertEquals(listOf(1,1,2), segments(rows).map { it.points.size })
        assertEquals("USD -10.00", amount(rows.first().actual, "USD", Locale.US))
        assertEquals("Sin datos", amount(null, "DOP", Locale.forLanguageTag("es-419")))
    }
}
