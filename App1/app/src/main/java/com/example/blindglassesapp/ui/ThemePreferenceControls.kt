package com.example.blindglassesapp.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.blindglassesapp.ui.theme.AppThemePreference

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ThemePreferenceChipRow(
    current: AppThemePreference,
    onChange: (AppThemePreference) -> Unit,
    modifier: Modifier = Modifier,
) {
    val modes = listOf(AppThemePreference.LIGHT, AppThemePreference.DARK)
    val labels = listOf("淺色", "深色")
    SingleChoiceSegmentedButtonRow(modifier = modifier.fillMaxWidth()) {
        modes.forEachIndexed { index, mode ->
            SegmentedButton(
                shape = SegmentedButtonDefaults.itemShape(
                    index = index,
                    count = modes.size,
                ),
                onClick = { onChange(mode) },
                selected = mode == current,
            ) {
                Text(
                    labels[index],
                    maxLines = 1,
                    style = MaterialTheme.typography.labelLarge,
                )
            }
        }
    }
}

@Composable
fun ThemePreferenceOverflowMenu(
    current: AppThemePreference,
    onChange: (AppThemePreference) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier = modifier) {
        IconButton(onClick = { expanded = true }) {
            Text("外觀", style = MaterialTheme.typography.labelLarge)
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.widthIn(min = 176.dp),
        ) {
            DropdownMenuItem(
                text = { Text("淺色${if (current == AppThemePreference.LIGHT) " ✓" else ""}") },
                onClick = {
                    onChange(AppThemePreference.LIGHT)
                    expanded = false
                },
            )
            DropdownMenuItem(
                text = { Text("深色${if (current == AppThemePreference.DARK) " ✓" else ""}") },
                onClick = {
                    onChange(AppThemePreference.DARK)
                    expanded = false
                },
            )
        }
    }
}
