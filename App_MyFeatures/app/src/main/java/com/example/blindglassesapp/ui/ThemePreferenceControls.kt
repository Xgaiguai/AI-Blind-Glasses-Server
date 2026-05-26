package com.example.blindglassesapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.blindglassesapp.ui.theme.AppThemePreference
import com.example.blindglassesapp.viewmodel.MainViewModel

@Composable
fun ThemePreferenceControls(viewModel: MainViewModel) {
    val currentTheme by viewModel.themePreference.collectAsState()

    Text(
        text = "外觀主題設定",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold
    )
    Spacer(modifier = Modifier.height(12.dp))

    Column {
        AppThemePreference.entries.forEach { pref ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                RadioButton(
                    selected = currentTheme == pref,
                    onClick = { viewModel.setTheme(pref) }
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = when (pref) {
                        AppThemePreference.LIGHT -> "淺色模式"
                        AppThemePreference.DARK -> "深色模式"
                        AppThemePreference.SYSTEM -> "跟隨系統設定"
                    },
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}
