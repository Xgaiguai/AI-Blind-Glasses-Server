package com.example.blindglassesapp

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModelProvider
import com.example.blindglassesapp.ble.BleService
import com.example.blindglassesapp.tts.TtsManager
import com.example.blindglassesapp.viewmodel.MainViewModel

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: MainViewModel
    private lateinit var ttsManager: TtsManager

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            if (!viewModel.isBluetoothEnabled) {
                @Suppress("DEPRECATION")
                startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            } else {
                startBleService()
                viewModel.startScan()
            }
        } else {
            Toast.makeText(this, "需要權限才能掃描藍牙", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        viewModel = ViewModelProvider(this)[MainViewModel::class.java]
        ttsManager = TtsManager(this)

        setContent {
            BlindGlassesApp(
                onRequestBleScan = { checkPermissionsAndScan() },
                ttsManager = ttsManager,
            )
        }

        // 如果已經有權限了，一開 App 就啟動 Service；否則等按下掃描再啟動
        if (hasRequiredPermissions()) {
            startBleService()
        }
    }

    private fun startBleService() {
        val serviceIntent = Intent(this, BleService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        ttsManager.release()
    }

    private fun hasRequiredPermissions(): Boolean {
        val required = getRequiredPermissionsList()
        return required.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun getRequiredPermissionsList(): List<String> {
        val required = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            required.add(Manifest.permission.BLUETOOTH_SCAN)
            required.add(Manifest.permission.BLUETOOTH_CONNECT)
            required.add(Manifest.permission.ACCESS_FINE_LOCATION)
            required.add(Manifest.permission.ACCESS_COARSE_LOCATION)
        } else {
            required.add(Manifest.permission.BLUETOOTH)
            required.add(Manifest.permission.BLUETOOTH_ADMIN)
            required.add(Manifest.permission.ACCESS_FINE_LOCATION)
            required.add(Manifest.permission.ACCESS_COARSE_LOCATION)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            required.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        return required
    }

    private fun checkPermissionsAndScan() {
        val required = getRequiredPermissionsList()

        val missing = required.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            requestPermissionLauncher.launch(missing.toTypedArray())
        } else {
            // 所有權限都拿到了，這時候才能安全地檢查藍牙有沒有開啟
            if (!viewModel.isBluetoothEnabled) {
                @Suppress("DEPRECATION")
                startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
                return
            }
            startBleService()
            viewModel.startScan()
        }
    }
}
