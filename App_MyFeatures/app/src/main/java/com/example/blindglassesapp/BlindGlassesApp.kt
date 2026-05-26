package com.example.blindglassesapp

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.blindglassesapp.tts.TtsManager
import com.example.blindglassesapp.ui.AccessibilityScreen
import com.example.blindglassesapp.ui.HomeScreen
import com.example.blindglassesapp.ui.LoadingOverlay
import com.example.blindglassesapp.ui.theme.BlindGlassesAppTheme
import com.example.blindglassesapp.viewmodel.MainViewModel

@Composable
fun BlindGlassesApp(
    onRequestBleScan: () -> Unit,
    ttsManager: TtsManager,
    viewModel: MainViewModel = viewModel()
) {
    val themePrefState by viewModel.themePreference.collectAsState()
    var showAccessibilityScreen by rememberSaveable { mutableStateOf(false) }
    var hasAnnouncedWelcome by rememberSaveable { mutableStateOf(false) }

    BlindGlassesAppTheme(
        darkTheme = themePrefState.isDarkMode(viewModel.getApplication<android.app.Application>())
    ) {
        Surface(modifier = Modifier.fillMaxSize()) {
            if (showAccessibilityScreen) {
                BackHandler { showAccessibilityScreen = false }
                AccessibilityScreen(
                    viewModel = viewModel,
                    ttsManager = ttsManager,
                    onBack = { showAccessibilityScreen = false }
                )
            } else {
                HomeScreen(
                    onRequestBleScan = onRequestBleScan,
                    onOpenAccessibility = { showAccessibilityScreen = true },
                    viewModel = viewModel,
                    ttsManager = ttsManager,
                    hasAnnouncedWelcome = hasAnnouncedWelcome,
                    onWelcomeAnnounced = { hasAnnouncedWelcome = true }
                )
                LoadingOverlay(viewModel = viewModel)
            }
        }
    }
}

