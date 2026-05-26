package com.example.blindglassesapp.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.viewmodel.MainViewModel

@Composable
fun LoadingOverlay(viewModel: MainViewModel) {
    val bleState by viewModel.bleState.collectAsState()
    val isConnecting = bleState is BleConnectionState.Connecting

    if (isConnecting) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = Color.Black.copy(alpha = 0.35f)
        ) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = Color.White)
            }
        }
    }
}
