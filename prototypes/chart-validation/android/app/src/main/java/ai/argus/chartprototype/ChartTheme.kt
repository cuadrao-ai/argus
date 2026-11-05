// Standalone reuse of the licensed native typography and neutral theme in #730.
package ai.argus.chartprototype

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val display = FontFamily(Font(R.font.space_grotesk, FontWeight.Medium))
private val body = FontFamily(Font(R.font.inter_variable))
private val typography = Typography(
    displaySmall = TextStyle(fontFamily = display, fontWeight = FontWeight.Medium, fontSize = 36.sp, lineHeight = 40.sp),
    headlineLarge = TextStyle(fontFamily = display, fontWeight = FontWeight.Medium, fontSize = 32.sp, lineHeight = 38.sp),
    headlineMedium = TextStyle(fontFamily = display, fontWeight = FontWeight.Medium, fontSize = 28.sp, lineHeight = 34.sp),
    headlineSmall = TextStyle(fontFamily = display, fontWeight = FontWeight.Medium, fontSize = 24.sp, lineHeight = 30.sp),
    titleLarge = TextStyle(fontFamily = display, fontWeight = FontWeight.Medium, fontSize = 22.sp, lineHeight = 28.sp),
    titleMedium = TextStyle(fontFamily = body, fontWeight = FontWeight.Medium, fontSize = 16.sp, lineHeight = 24.sp),
    bodyLarge = TextStyle(fontFamily = body, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontFamily = body, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontFamily = body, fontWeight = FontWeight.Normal, fontSize = 12.sp, lineHeight = 18.sp),
    titleSmall = TextStyle(fontFamily = body, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = body, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 18.sp),
    labelSmall = TextStyle(fontFamily = body, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontFamily = body, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 20.sp),
)
private val light = lightColorScheme(
    primary = Color(0xFF191C1F), onPrimary = Color.White,
    background = Color.White, onBackground = Color(0xFF191C1F),
    surface = Color.White, onSurface = Color(0xFF191C1F),
    surfaceVariant = Color(0xFFF4F4F4), onSurfaceVariant = Color(0xFF505A63),
    secondary = Color(0xFF505A63), onSecondary = Color.White,
    surfaceTint = Color.Transparent, surfaceContainerHigh = Color(0xFFF4F4F4),
    surfaceContainerHighest = Color(0xFFE2E5E7),
    surfaceContainer = Color(0xFFF4F4F4), surfaceContainerLow = Color(0xFFF9F9F9),
    secondaryContainer = Color(0xFFF4F4F4), onSecondaryContainer = Color(0xFF191C1F),
    outline = Color(0xFFC9C9CD), error = Color(0xFF98482F),
)
private val dark = darkColorScheme(
    primary = Color(0xFFF4F4F5), onPrimary = Color(0xFF191C1F),
    background = Color(0xFF191C1F), onBackground = Color(0xFFF4F4F5),
    surface = Color(0xFF191C1F), onSurface = Color(0xFFF4F4F5),
    surfaceVariant = Color(0xFF24282C), onSurfaceVariant = Color(0xFFB4BBC2),
    secondary = Color(0xFFB4BBC2), onSecondary = Color(0xFF191C1F),
    surfaceTint = Color.Transparent, surfaceContainerHigh = Color(0xFF24282C),
    surfaceContainerHighest = Color(0xFF3A4148),
    surfaceContainer = Color(0xFF24282C), surfaceContainerLow = Color(0xFF151719),
    secondaryContainer = Color(0xFF24282C), onSecondaryContainer = Color(0xFFF4F4F5),
    outline = Color(0xFF4B5259), error = Color(0xFFE08D70),
)

@Composable
fun ArgusChartTheme(isDark: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isDark) dark else light, typography = typography, content = content)
}
