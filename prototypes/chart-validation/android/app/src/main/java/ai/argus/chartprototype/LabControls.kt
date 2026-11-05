package ai.argus.chartprototype

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun LabControls(cases: List<Scenario>, caseIndex: Int, language: String, theme: String,
                onCase: (Int) -> Unit, onLanguage: () -> Unit, onTheme: (String) -> Unit) {
    val es = language == "es-419"
    fun themeName(mode: String) = if(!es) mode else when(mode) { "Dark" -> "Oscuro"; "Light" -> "Claro"; else -> "Sistema" }
    var casesOpen by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { casesOpen = true }, modifier = Modifier.testTag("scenario")) { Text(cases[caseIndex].titles.getValue(language)) }
        DropdownMenu(casesOpen, { casesOpen = false }) {
            cases.forEachIndexed { index, item -> DropdownMenuItem(text = { Text(item.titles.getValue(language)) }, onClick = { onCase(index); casesOpen = false }, modifier = Modifier.testTag("case-${item.id}")) }
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextButton(onClick = onLanguage, modifier = Modifier.testTag("locale")) { Text(if(es) "English" else "Español") }
        var themesOpen by remember { mutableStateOf(false) }
        Box {
            OutlinedButton(onClick = { themesOpen = true }, modifier = Modifier.testTag("theme")) { Text(themeName(theme)) }
            DropdownMenu(themesOpen, { themesOpen = false }) {
                listOf("System", "Light", "Dark").forEach { mode -> DropdownMenuItem(text = { Text(themeName(mode)) }, onClick = { onTheme(mode); themesOpen = false }, modifier = Modifier.testTag("theme-$mode")) }
            }
        }
    }
}
