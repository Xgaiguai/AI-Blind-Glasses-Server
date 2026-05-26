package com.example.blindglassesapp.ui.theme

import android.content.Context
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF90CAF9),
    onPrimary = Color(0xFF0D47A1),
    primaryContainer = Color(0xFF1565C0),
    onPrimaryContainer = Color(0xFFBBDEFB),
    secondary = Color(0xFF81D4FA),
    onSecondary = Color(0xFF013A52),
    surface = Color(0xFF121212),
    onSurface = Color(0xFFE1E1E1),
    background = Color(0xFF1A1A2E),
    onBackground = Color(0xFFE1E1E1),
    surfaceVariant = Color(0xFF2A2A3E),
    onSurfaceVariant = Color(0xFFBBBBCC),
    error = Color(0xFFEF9A9A),
    onError = Color(0xFF69000A)
)

private val LightColorScheme = lightColorScheme(
    primary = Color(0xFF1976D2),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFBBDEFB),
    onPrimaryContainer = Color(0xFF0D47A1),
    secondary = Color(0xFF0288D1),
    onSecondary = Color.White,
    surface = Color(0xFFF5F5F5),
    onSurface = Color(0xFF111111),
    background = Color(0xFFFFFFFF),
    onBackground = Color(0xFF111111),
    surfaceVariant = Color(0xFFE3E3EF),
    onSurfaceVariant = Color(0xFF44446A),
    error = Color(0xFFB71C1C),
    onError = Color.White
)

enum class AppThemePreference {
    LIGHT, DARK, SYSTEM;

    fun isDarkMode(context: Context): Boolean {
        val isSystemDark = (context.resources.configuration.uiMode
                and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
                android.content.res.Configuration.UI_MODE_NIGHT_YES
        return when (this) {
            LIGHT -> false
            DARK -> true
            SYSTEM -> isSystemDark
        }
    }
}

@Composable
fun BlindGlassesAppTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}