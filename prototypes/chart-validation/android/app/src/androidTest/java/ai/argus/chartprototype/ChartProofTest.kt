package ai.argus.chartprototype

import android.os.SystemClock
import androidx.core.graphics.toColorInt
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.Locale

class ChartProofTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val cases get() = context.assets.open("series.json").bufferedReader().use { parseFixtures(it.readText()) }
    private fun choose(id: String) {
        compose.onNodeWithTag("scenario").performScrollTo().performClick()
        compose.onNodeWithTag("case-$id").performClick()
        compose.onNodeWithText("Argus").performScrollTo()
        compose.waitForIdle()
    }
    private fun readout() = compose.onNodeWithTag("readout").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString { it.text }
    private fun screenshot(name: String, scrollToTop: Boolean = true) {
        if(scrollToTop) compose.onNodeWithText("Argus").performScrollTo()
        compose.waitForIdle()
        val dark = compose.onNodeWithTag("appearance").fetchSemanticsNode().config[SemanticsProperties.StateDescription] == "dark"
        val expected = (if(dark) "#191c1f" else "#ffffff").toColorInt()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val deadline = SystemClock.uptimeMillis() + 5000
        var bitmap: android.graphics.Bitmap
        do {
            compose.mainClock.advanceTimeByFrame()
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            bitmap = automation.takeScreenshot()
            if(bitmap.getPixel(10, bitmap.height / 2) == expected) break
            SystemClock.sleep(50)
        } while(SystemClock.uptimeMillis() < deadline)
        assertEquals("Capture must show resolved appearance, not the prior frame", expected, bitmap.getPixel(10, bitmap.height / 2))
        File(context.getExternalFilesDir(null), "$name.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun axisCentsUseReadoutPrecision() {
        val single = cases.first { it.id == "single" }
        val point = single.points.single()
        choose(single.id)
        compose.onNodeWithTag("next").performClick()
        compose.onNodeWithText(numberFormat(Locale.US, point.actual!!).format(point.actual)).assertIsDisplayed()
        assertTrue(readout().contains(amount(point.actual, single.currency, Locale.US)))
        screenshot("axis-cents-single")
        compose.onNodeWithTag("locale").performScrollTo().performClick()
        compose.onNodeWithText("Argus").performScrollTo()
        compose.onNodeWithText(numberFormat(Locale.forLanguageTag("es-419"), point.actual!!).format(point.actual)).assertIsDisplayed()
        screenshot("axis-cents-single-es")
    }
    @Test fun fixturesAndSegmentsPreserveEveryFact() {
        cases.forEach { case ->
            listOf(false, true).forEach { projected ->
                val pieces = segments(case.points).filter { it.projected == projected }
                assertEquals(case.points.filter { (if(projected) it.projected else it.actual) != null }, pieces.flatMap { it.points })
                pieces.forEach { segment ->
                    segment.points.zipWithNext().forEach { (a,b) -> assertEquals(case.points.indexOf(a) + 1, case.points.indexOf(b)) }
                }
            }
            if (case.points.isNotEmpty()) {
                assertEquals(0, nearest(case.points, -1f))
                assertEquals(case.points.lastIndex, nearest(case.points, 2f))
            } else assertNull(nearest(case.points, .5f))
        }
    }
    @Test fun allCasesAccessibleReadoutAndFormatting() {
        for (case in cases) {
            choose(case.id)
            if(case.points.isEmpty()) {
                compose.onNodeWithTag("next").assertIsNotEnabled()
                screenshot("empty")
            } else {
                compose.onNodeWithTag("next").performClick()
                assertTrue(readout().contains(date(case.points.first().time, Locale.US)))
                compose.onNodeWithTag("reset").performClick()
                compose.onNodeWithTag("previous").performClick()
                assertTrue(readout().contains(date(case.points.last().time, Locale.US)))
                screenshot(case.id)
            }
        }
        val stress = cases.first { it.id == "stress" }
        choose(stress.id)
        for (point in stress.points) {
            compose.onNodeWithTag("next").performClick()
            assertTrue(readout().contains(date(point.time, Locale.US)))
            assertTrue(readout().contains("Actual: " + amount(point.actual, stress.currency, Locale.US)))
            assertTrue(readout().contains("Projected: " + amount(point.projected, stress.currency, Locale.US)))
        }
        compose.onNodeWithTag("locale").performScrollTo().performClick()
        val spanish = Locale.forLanguageTag("es-419")
        assertTrue(readout().contains(date(stress.points.last().time, spanish)))
        assertTrue(readout().contains("Real: " + amount(stress.points.last().actual, stress.currency, spanish)))
        compose.onNodeWithTag("theme").performScrollTo().performClick()
        compose.onNodeWithTag("theme-Dark").performClick()
        screenshot("spanish-dark")
        compose.onNodeWithTag("theme").performScrollTo().performClick()
        compose.onNodeWithTag("theme-Light").performClick()
        screenshot("spanish-light")
        compose.onNodeWithTag("theme").performScrollTo().performClick()
        compose.onNodeWithTag("theme-System").performClick()
        screenshot("spanish-system")
    }
    @Test fun dragReleaseCancellationResetAndScroll() {
        val stress = cases.first { it.id == "stress" }
        choose(stress.id)
        compose.onNodeWithTag("scrub").performTouchInput { swipe(Offset(1f, centerY), Offset(width.toFloat()-1, centerY), 600) }
        assertTrue(readout().contains(date(stress.points.last().time, Locale.US)))
        screenshot("scrub-endpoint")
        val retained = readout()
        compose.onNodeWithTag("scrub").performTouchInput {
            down(Offset(width.toFloat()-2, centerY))
            moveTo(Offset(width * .4f, centerY), 200)
            cancel()
        }
        assertEquals(retained, readout())
        compose.onNodeWithTag("scrub").performTouchInput { swipe(Offset(width.toFloat()-1, centerY), Offset(1f, centerY), 500) }
        assertTrue(readout().contains(date(stress.points.first().time, Locale.US)))
        compose.onNodeWithTag("reset").performClick()
        assertTrue(readout().startsWith("Select"))
        val before = compose.onNodeWithTag("page").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange].value()
        compose.onNodeWithTag("scrub").performTouchInput { swipe(Offset(centerX, height*.9f), Offset(centerX, 1f), 500) }
        val after = compose.onNodeWithTag("page").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange].value()
        assertTrue("Vertical chart gesture must scroll page", after > before)
        screenshot("vertical-scroll", scrollToTop = false)
    }
    @Test fun systemAppearanceFollowsDeviceSetting() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        try {
            device.executeShellCommand("cmd uimode night yes")
            compose.waitUntil(10000) { compose.onNodeWithTag("appearance").fetchSemanticsNode().config[SemanticsProperties.StateDescription] == "dark" }
            screenshot("system-os-dark")
            device.executeShellCommand("cmd uimode night no")
            compose.waitUntil(10000) { compose.onNodeWithTag("appearance").fetchSemanticsNode().config[SemanticsProperties.StateDescription] == "light" }
            screenshot("system-os-light")
        } finally { device.executeShellCommand("cmd uimode night auto") }
    }
    @Test fun enlargedTextRetainsReadoutGeometry() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        try {
            device.executeShellCommand("settings put system font_scale 1.5")
            compose.waitUntil(10000) { compose.activity.resources.configuration.fontScale >= 1.5f }
            choose("stress")
            val before = compose.onNodeWithTag("readout").getUnclippedBoundsInRoot().let { it.bottom.value - it.top.value }
            compose.onNodeWithTag("next").performScrollTo().performClick()
            val after = compose.onNodeWithTag("readout").getUnclippedBoundsInRoot().let { it.bottom.value - it.top.value }
            assertEquals("Readout slots stay stable at enlarged font size", before, after, 1f)
            screenshot("enlarged-text")
        } finally { device.executeShellCommand("settings put system font_scale 1.0") }
    }
    @Test fun reducedMotionKeepsDirectSelection() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val settings = listOf("animator_duration_scale", "transition_animation_scale", "window_animation_scale")
        val original = settings.associateWith { device.executeShellCommand("settings get global $it").trim() }
        try {
            settings.forEach { device.executeShellCommand("settings put global $it 0") }
            choose("stress")
            compose.onNodeWithTag("next").performClick()
            assertTrue(readout().contains(date(cases.first { it.id == "stress" }.points.first().time, Locale.US)))
            screenshot("reduced-motion")
        } finally { original.forEach { (key, value) -> device.executeShellCommand(if(value == "null") "settings delete global $key" else "settings put global $key $value") } }
    }
    @Test fun longSeriesMeasuredInteraction() {
        val start = SystemClock.elapsedRealtimeNanos()
        choose("long")
        val ready = SystemClock.elapsedRealtimeNanos()
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        device.executeShellCommand("dumpsys gfxinfo ai.argus.chartprototype reset")
        val bounds = compose.onNodeWithTag("scrub").fetchSemanticsNode().boundsInWindow
        repeat(12) { n ->
            val a = (bounds.left + bounds.width * if(n % 2 == 0) .15f else .85f).toInt()
            val b = (bounds.left + bounds.width * if(n % 2 == 0) .85f else .15f).toInt()
            val before = readout()
            device.executeShellCommand("input swipe $a ${bounds.center.y.toInt()} $b ${bounds.center.y.toInt()} 300")
            compose.waitForIdle()
            assertNotEquals("Paced swipe must change the chart readout", before, readout())
        }
        val finish = SystemClock.elapsedRealtimeNanos()
        val report = "scenario_switch_to_idle_ms=${(ready-start)/1e6}\n12_shell_300ms_swipes_including_test_sync_ms=${(finish-ready)/1e6}\npoints=${cases.first { it.id == "long" }.points.size}\n"
        File(context.getExternalFilesDir(null), "interaction-measurements.txt").writeText(report)
        val frames = device.executeShellCommand("dumpsys gfxinfo ai.argus.chartprototype framestats")
        val frameCount = Regex("Total frames rendered: ([0-9]+)").find(frames)?.groupValues?.get(1)?.toIntOrNull()
        assertTrue("Frame sample must report a positive rendered frame count", frameCount != null && frameCount > 0)
        File(context.getExternalFilesDir(null), "long-series-gfxinfo.txt").writeText(frames)
        screenshot("long-scrub")
    }
}
