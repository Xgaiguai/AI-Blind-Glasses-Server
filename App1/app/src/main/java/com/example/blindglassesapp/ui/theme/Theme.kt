package com.example.blindglassesapp.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val AppLightColorScheme = lightColorScheme(
    primary = AccentPrimaryLight,
    onPrimary = OnAccentPrimaryLight,
    primaryContainer = Color(0xFFD0E8FF),
    onPrimaryContainer = Color(0xFF001C38),
    secondary = Color(0xFF3D3D3D),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE8E8E8),
    onSecondaryContainer = Color(0xFF1A1A1A),
    tertiary = Color(0xFF5C5C5C),
    onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF2F2F2),
    onBackground = Color(0xFF0A0A0A),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF0A0A0A),
    surfaceVariant = Color(0xFFECECEC),
    onSurfaceVariant = Color(0xFF4A4A4A),
    outline = ChromeOutlineLight,
    outlineVariant = Color(0xFFE0E0E0),
    error = Color(0xFFBA1A1A),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002),
    scrim = Color(0xCC000000),
)

private val AppDarkColorScheme = darkColorScheme(
    primary = PrimaryBlue,
    onPrimary = OnPrimaryBlue,
    primaryContainer = Color(0xFF1E3A5F),
    onPrimaryContainer = Color(0xFFD0E8FF),
    secondary = SecondaryMint,
    onSecondary = Color(0xFF003D29),
    secondaryContainer = Color(0xFF1A3D2E),
    onSecondaryContainer = Color(0xFFA8F0D4),
    tertiary = Color(0xFFB0B0B0),
    onTertiary = Color(0xFF222222),
    background = DarkBackground,
    onBackground = TextPrimary,
    surface = DarkSurface,
    onSurface = TextPrimary,
    surfaceVariant = Color(0xFF242840),
    onSurfaceVariant = TextSecondary,
    outline = ChromeOutlineDark,
    outlineVariant = Color(0xFF2A2E42),
    error = ErrorRose,
    onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A),
    onErrorContainer = Color(0xFFFFDAD6),
    scrim = Color(0xE6000000),
)

@Composable
fun BlindGlassesAppTheme(
    darkTheme: Boolean,
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) AppDarkColorScheme else AppLightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content,
    )
}
