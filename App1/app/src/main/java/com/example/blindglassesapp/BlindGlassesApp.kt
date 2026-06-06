package com.example.blindglassesapp

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Sensors
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.blindglassesapp.data.UiThemeStorage
import com.example.blindglassesapp.ui.HomeScreen
import com.example.blindglassesapp.ui.MonitorScreen
import com.example.blindglassesapp.ui.AccessibilityScreen
import com.example.blindglassesapp.ui.SettingsScreen
import com.example.blindglassesapp.ui.theme.AppThemePreference
import com.example.blindglassesapp.ui.theme.BlindGlassesAppTheme
import com.example.blindglassesapp.viewmodel.MainViewModel
import com.example.blindglassesapp.tts.TtsManager

@Composable
fun BlindGlassesApp(
    onRequestBleScan: () -> Unit,
    ttsManager: TtsManager,
) {
    val context = LocalContext.current
    val themeStorage = remember { UiThemeStorage(context) }
    var themePreference by remember { mutableStateOf(themeStorage.load()) }

    fun persistTheme(mode: AppThemePreference) {
        themePreference = mode
        themeStorage.save(mode)
    }

    val useDarkTheme = themePreference == AppThemePreference.DARK

    BlindGlassesAppTheme(darkTheme = useDarkTheme) {
        val viewModel: MainViewModel = viewModel()
        var activeTab by remember { mutableStateOf("home") }
        var showAccessibility by remember { mutableStateOf(false) }

        BackHandler(enabled = !showAccessibility && activeTab != "home") {
            activeTab = "home"
        }

        if (showAccessibility) {
            AccessibilityScreen(
                viewModel = viewModel,
                ttsManager = ttsManager,
                onBack = { showAccessibility = false }
            )
        } else {
            Scaffold(
                bottomBar = {
                    NavigationBar(
                        containerColor = androidx.compose.material3.MaterialTheme.colorScheme.surface,
                    ) {
                        NavigationBarItem(
                            selected = activeTab == "home",
                            onClick = { activeTab = "home" },
                            icon = { Icon(Icons.Default.Home, contentDescription = "首頁") },
                            label = { Text("首頁") }
                        )
                        NavigationBarItem(
                            selected = activeTab == "monitor",
                            onClick = { activeTab = "monitor" },
                            icon = { Icon(Icons.Default.Sensors, contentDescription = "即時監看") },
                            label = { Text("即時監看") }
                        )
                        NavigationBarItem(
                            selected = activeTab == "settings",
                            onClick = { activeTab = "settings" },
                            icon = { Icon(Icons.Default.Settings, contentDescription = "設置") },
                            label = { Text("設置") }
                        )
                    }
                }
            ) { paddingValues ->
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(bottom = paddingValues.calculateBottomPadding())
                ) {
                    when (activeTab) {
                        "home" -> HomeScreen(
                            viewModel = viewModel,
                            onScanClick = onRequestBleScan,
                            themePreference = themePreference,
                            onThemePreferenceChange = { persistTheme(it) },
                            onMonitorClick = {
                                viewModel.dismissDeviceListResults()
                                activeTab = "monitor"
                            },
                            onOpenAccessibility = {
                                viewModel.dismissDeviceListResults()
                                showAccessibility = true
                            }
                        )
                        "monitor" -> MonitorScreen(
                            onBack = { activeTab = "home" },
                        )
                        "settings" -> SettingsScreen(
                            viewModel = viewModel,
                            themePreference = themePreference,
                            onThemePreferenceChange = { persistTheme(it) },
                            onScanClick = onRequestBleScan,
                            onOpenAccessibility = {
                                viewModel.dismissDeviceListResults()
                                showAccessibility = true
                            }
                        )
                    }
                }
            }
        }
    }
}

