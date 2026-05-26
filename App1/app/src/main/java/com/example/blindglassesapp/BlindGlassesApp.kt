package com.example.blindglassesapp



import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.blindglassesapp.data.UiThemeStorage
import com.example.blindglassesapp.ui.HomeScreen
import com.example.blindglassesapp.ui.MonitorScreen
import com.example.blindglassesapp.ui.AccessibilityScreen
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

        val navController = rememberNavController()

        val viewModel: MainViewModel = viewModel()



        NavHost(navController = navController, startDestination = "home") {

            composable("home") {

                HomeScreen(

                    viewModel = viewModel,

                    onScanClick = onRequestBleScan,

                    themePreference = themePreference,

                    onThemePreferenceChange = { persistTheme(it) },

                    onMonitorClick = {
                        viewModel.dismissDeviceListResults()
                        navController.navigate("monitor")
                    },
                    onOpenAccessibility = {
                        viewModel.dismissDeviceListResults()
                        navController.navigate("accessibility")
                    }
                )
            }
            composable("accessibility") {
                AccessibilityScreen(
                    viewModel = viewModel,
                    ttsManager = ttsManager,
                    onBack = { navController.popBackStack() }
                )
            }

            composable("monitor") {

                MonitorScreen(

                    onBack = { navController.popBackStack() },

                    themePreference = themePreference,

                    onThemePreferenceChange = { persistTheme(it) },

                )

            }

        }

    }

}

