package ai.argus.chartprototype

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.core.view.WindowCompat
import androidx.core.graphics.toColorInt
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import com.patrykandpatrick.vico.compose.cartesian.*
import com.patrykandpatrick.vico.compose.cartesian.layer.*
import com.patrykandpatrick.vico.compose.common.fill
import com.patrykandpatrick.vico.core.cartesian.data.*
import com.patrykandpatrick.vico.core.cartesian.layer.LineCartesianLayer
import com.patrykandpatrick.vico.core.common.component.ShapeComponent
import com.patrykandpatrick.vico.core.common.shape.CorneredShape
import com.patrykandpatrick.vico.core.cartesian.Zoom
import com.patrykandpatrick.vico.compose.cartesian.layer.cartesianLayerPadding
import java.util.Locale

class MainActivity : ComponentActivity() {
    private var chartIsDark = false
    private fun updateSystemBars(dark: Boolean) {
        chartIsDark = dark
        window.decorView.post {
            WindowCompat.getInsetsController(window, window.decorView).apply {
                isAppearanceLightStatusBars = !chartIsDark
                isAppearanceLightNavigationBars = !chartIsDark
            }
        }
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) updateSystemBars(chartIsDark)
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val cases = assets.open("series.json").bufferedReader().use { parseFixtures(it.readText()) }
        val palette = assets.open("visual-style.json").bufferedReader().use { org.json.JSONObject(it.readText()) }
        require(palette.getString("version") == "argus.chart-prototype-style/v1")
        setContent { Prototype(cases, palette, ::updateSystemBars) }
    }
}

@Composable
fun Prototype(cases: List<Scenario>, palette: org.json.JSONObject, onAppearance: (Boolean) -> Unit) {
    var caseIndex by rememberSaveable { mutableIntStateOf(0) }
    var selected by rememberSaveable { mutableStateOf<Int?>(null) }
    var language by rememberSaveable { mutableStateOf("en") }
    var theme by rememberSaveable { mutableStateOf("System") }
    val es = language == "es-419"
    val locale = Locale.forLanguageTag(if (es) "es-419" else "en-US")
    val scenario = cases[caseIndex]
    fun t(en: String, spanish: String) = if (es) spanish else en
    val dark = theme == "Dark" || (theme == "System" && isSystemInDarkTheme())
    SideEffect { onAppearance(dark) }
    val resolvedPalette = palette.getJSONObject(if(dark) "dark" else "light")
    val actualColor = Color(resolvedPalette.getString("actual").toColorInt())
    val projectedColor = Color(resolvedPalette.getString("projected").toColorInt())
    ArgusChartTheme(dark) {
        Surface(Modifier.fillMaxSize().testTag("appearance").semantics { stateDescription = if(dark) "dark" else "light" }) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).testTag("page").padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("Argus", style = MaterialTheme.typography.headlineSmall)
                Text(t("SYNTHETIC EXAMPLE", "EJEMPLO SINTÉTICO"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(scenario.titles.getValue(language), style = MaterialTheme.typography.titleLarge)
                val sample = selected?.let(scenario.points::get)
                val scale = androidx.compose.ui.platform.LocalDensity.current.fontScale
                Column(Modifier.fillMaxWidth().testTag("readout").semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
                    Text(if(sample != null) date(sample.time, locale) else if(scenario.points.isEmpty()) t("No observations", "Sin observaciones") else t("Select a date", "Selecciona una fecha"), Modifier.heightIn(min = (24 * scale).dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(t("Actual", "Real") + ": " + if(sample != null) amount(sample.actual, scenario.currency, locale) else "—", Modifier.fillMaxWidth().heightIn(min = (60 * scale).dp), style = MaterialTheme.typography.headlineSmall)
                    Text(t("Projected", "Proyectado") + ": " + if(sample != null) amount(sample.projected, scenario.currency, locale) else "—", Modifier.fillMaxWidth().heightIn(min = (24 * scale).dp), style = MaterialTheme.typography.bodyMedium)
                    Text(t("Contribution", "Aporte") + ": " + if(sample != null) amount(sample.contribution, scenario.currency, locale) else "—", Modifier.fillMaxWidth().heightIn(min = (24 * scale).dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                    SeriesLegend(t("Actual", "Real"), actualColor, false)
                    SeriesLegend(t("Projected", "Proyectado"), projectedColor, true)
                }
                key(scenario.id) { FinancialChart(scenario, selected, { selected = it }, t("No data", "Sin datos"), locale, actualColor, projectedColor) }
                if (scenario.points.isNotEmpty()) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(date(scenario.points.first().time, locale), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if(scenario.points.size > 1) Text(date(scenario.points.last().time, locale), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(onClick = { selected = selected?.minus(1)?.coerceAtLeast(0) ?: scenario.points.lastIndex }, enabled = scenario.points.isNotEmpty(), modifier = Modifier.testTag("previous")) { Text(t("Previous", "Anterior")) }
                    OutlinedButton(onClick = { selected = selected?.plus(1)?.coerceAtMost(scenario.points.lastIndex) ?: 0 }, enabled = scenario.points.isNotEmpty(), modifier = Modifier.testTag("next")) { Text(t("Next", "Siguiente")) }
                    TextButton(onClick = { selected = null }, modifier = Modifier.testTag("reset")) { Text(t("Reset", "Borrar")) }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = .45f))
                Text(t("Prototype controls", "Controles del prototipo"), style = MaterialTheme.typography.titleMedium)
                LabControls(cases, caseIndex, language, theme,
                    onCase = { caseIndex = it; selected = null },
                    onLanguage = { language = if(es) "en" else "es-419" },
                    onTheme = { theme = it })
                Text("${scenario.currency} · ${t("major currency units · UTC civil dates", "unidades monetarias · fechas civiles UTC")}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(t("Horizontal drag selects. Vertical drag scrolls. Release keeps the date; cancellation restores the prior selection. Use Previous and Next to read every date, including missing data.", "Arrastra horizontalmente para seleccionar y verticalmente para desplazar. Al soltar se conserva la fecha; al cancelar se restaura la selección anterior. Usa Anterior y Siguiente para leer todas las fechas, incluso las que no tienen datos."), style = MaterialTheme.typography.bodySmall)
                Text(t("Synthetic data only. No forecasts, returns, balances, provider calls or account data are calculated here.", "Solo datos sintéticos. Aquí no se calculan pronósticos, rendimientos ni saldos, ni se consultan proveedores o cuentas."), style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(160.dp))
                Text(t("End of scroll proof", "Fin de prueba de desplazamiento"), Modifier.testTag("footer"), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun SeriesLegend(label: String, color: Color, dashed: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Canvas(Modifier.width(24.dp).height(12.dp)) {
            drawLine(color, Offset(0f, center.y), Offset(size.width, center.y), 2.dp.toPx(), pathEffect = if(dashed) androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 3.dp.toPx())) else null)
        }
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun FinancialChart(scenario: Scenario, selection: Int?, onSelect: (Int?) -> Unit, empty: String, locale: Locale, actualColor: Color, projectedColor: Color) {
    val pieces = remember(scenario) { segments(scenario.points) }
    val currentSelection by rememberUpdatedState(selection)
    val currentSelect by rememberUpdatedState(onSelect)
    val foreground = MaterialTheme.colorScheme.onSurface
    val values = remember(scenario) { scenario.points.flatMap { listOfNotNull(it.actual, it.projected) } }
    val minY = (values.minOrNull() ?: 0.0).coerceAtMost(0.0)
    val maxY = (values.maxOrNull() ?: 1.0).coerceAtLeast(0.0).let { if(it == minY) it + 1 else it }
    val ticks = remember(minY, maxY) { axisTicks(minY, maxY) }
    Row(Modifier.fillMaxWidth()) {
        if(values.isNotEmpty()) Column(Modifier.width((52 * androidx.compose.ui.platform.LocalDensity.current.fontScale).dp).height(220.dp), verticalArrangement = Arrangement.SpaceBetween) {
            ticks.forEach { Text(numberFormat(locale, it).format(it), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        Box(Modifier.weight(1f).height(220.dp).testTag("chart")) {
        if(values.isNotEmpty()) Canvas(Modifier.fillMaxSize()) {
            ticks.forEach { val y = ((maxY - it) / (maxY - minY) * size.height).toFloat(); drawLine(foreground.copy(alpha = .12f), Offset(0f, y), Offset(size.width, y), 1f) }
        }
        if (pieces.isEmpty()) Text(empty, Modifier.align(Alignment.Center)) else {
            val lines = pieces.map { piece ->
                val color = if (piece.projected) projectedColor else actualColor
                val lineFill = LineCartesianLayer.LineFill.single(fill(color))
                LineCartesianLayer.rememberLine(
                    fill = lineFill,
                    stroke = if (piece.projected) LineCartesianLayer.LineStroke.dashed() else LineCartesianLayer.LineStroke.continuous(),
                    pointConnector = LineCartesianLayer.PointConnector.Sharp,
                    pointProvider = if (piece.points.size == 1) LineCartesianLayer.PointProvider.single(LineCartesianLayer.Point(ShapeComponent(fill(color), CorneredShape.Pill), 7f)) else null
                )
            }
            val model = remember(scenario) { CartesianChartModel(LineCartesianLayerModel.build {
                pieces.forEach { piece -> series(piece.points.map { it.time.toEpochDay() }, piece.points.map { (if (piece.projected) it.projected else it.actual)!! }) }
            }) }
            val first = scenario.points.first().time.toEpochDay().toDouble()
            val last = scenario.points.last().time.toEpochDay().toDouble()
            val range = remember(scenario) { CartesianLayerRangeProvider.fixed(minX = if(first == last) first - .5 else first, maxX = if(first == last) last + .5 else last, minY = minY, maxY = maxY) }
            CartesianChartHost(
                chart = rememberCartesianChart(rememberLineCartesianLayer(lineProvider = LineCartesianLayer.LineProvider.series(lines), rangeProvider = range), layerPadding = { cartesianLayerPadding() }),
                model = model,
                modifier = Modifier.fillMaxSize(),
                scrollState = rememberVicoScrollState(scrollEnabled = false),
                zoomState = rememberVicoZoomState(zoomEnabled = false, initialZoom = Zoom.Content)
            )
        }
        Canvas(Modifier.fillMaxSize().testTag("scrub").pointerInput(scenario.id) {
            var before: Int? = null
            detectHorizontalDragGestures(
                onDragStart = { offset -> before = currentSelection; currentSelect(nearest(scenario.points, offset.x / size.width)) },
                onHorizontalDrag = { change, _ -> currentSelect(nearest(scenario.points, change.position.x / size.width)); change.consume() },
                onDragEnd = {},
                onDragCancel = { currentSelect(before) }
            )
        }.semantics { contentDescription = if(empty == "Sin datos") "Gráfico. Usa Anterior y Siguiente para leer todas las fechas." else "Chart. Use Previous and Next to read every date." }) {
            selection?.let { val x = position(scenario.points, it) * size.width; drawLine(foreground, Offset(x, 0f), Offset(x, size.height), 2f) }
        }
    }
    }
}
