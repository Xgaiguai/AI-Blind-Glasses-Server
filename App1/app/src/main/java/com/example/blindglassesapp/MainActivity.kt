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
import androidx.lifecycle.lifecycleScope
import com.example.blindglassesapp.viewmodel.MainViewModel
import com.example.blindglassesapp.tts.TtsManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: MainViewModel
    private lateinit var ttsManager: TtsManager

    // ── 雙鍵長按觸發盲人模式的狀態追蹤 ──
    private var isVolumeUpPressed = false
    private var isVolumeDownPressed = false
    private var accessibilityShortcutJob: Job? = null

    private val enableBluetoothLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            viewModel.startScan()
        } else {
            Toast.makeText(this, "請啟用藍牙以連接眼鏡", Toast.LENGTH_SHORT).show()
        }
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            if (viewModel.isBluetoothEnabled) {
                viewModel.startScan()
            } else {
                promptEnableBluetooth()
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
                ttsManager = ttsManager
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        ttsManager.release()
    }

    private fun promptEnableBluetooth() {
        try {
            @Suppress("DEPRECATION")
            enableBluetoothLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
        } catch (e: Exception) {
            Toast.makeText(this, "無法啟用藍牙，請手動至系統設定開啟", Toast.LENGTH_LONG).show()
        }
    }

    private fun checkPermissionsAndScan() {
        if (!viewModel.isBluetoothSupported) {
            Toast.makeText(this, "此裝置不支援藍牙功能", Toast.LENGTH_LONG).show()
            return
        }

        val required = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            )
        } else {
            arrayOf(
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            )
        }

        val missing = required.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            requestPermissionLauncher.launch(missing.toTypedArray())
        } else {
            if (viewModel.isBluetoothEnabled) {
                viewModel.startScan()
            } else {
                promptEnableBluetooth()
            }
        }
    }

    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        val action = event.action
        val keyCode = event.keyCode

        // ── 模式一：音量調整模式啟用時 → 攔截單鍵，調整眼鏡音量 ──
        if (::viewModel.isInitialized && viewModel.isVolumeAdjustmentActive.value) {
            if (action == android.view.KeyEvent.ACTION_DOWN) {
                when (keyCode) {
                    android.view.KeyEvent.KEYCODE_VOLUME_UP -> {
                        val sent = viewModel.increaseVolume()
                        if (sent) {
                            ttsManager.speak("音量 ${viewModel.currentVolume.value}")
                        } else {
                            ttsManager.speak("調整失敗")
                        }
                        return true
                    }
                    android.view.KeyEvent.KEYCODE_VOLUME_DOWN -> {
                        val sent = viewModel.decreaseVolume()
                        if (sent) {
                            ttsManager.speak("音量 ${viewModel.currentVolume.value}")
                        } else {
                            ttsManager.speak("調整失敗")
                        }
                        return true
                    }
                }
            } else if (action == android.view.KeyEvent.ACTION_UP) {
                if (keyCode == android.view.KeyEvent.KEYCODE_VOLUME_UP || keyCode == android.view.KeyEvent.KEYCODE_VOLUME_DOWN) {
                    return true
                }
            }
            return true
        }

        // ── 模式二：音量調整模式未啟用 → 偵測雙鍵同時點按進入或退出盲人模式 ──
        if (::viewModel.isInitialized) {
            val isBlindMode = viewModel.isAccessibilityModeActive.value

            when (action) {
                android.view.KeyEvent.ACTION_DOWN -> {
                    when (keyCode) {
                        android.view.KeyEvent.KEYCODE_VOLUME_UP -> isVolumeUpPressed = true
                        android.view.KeyEvent.KEYCODE_VOLUME_DOWN -> isVolumeDownPressed = true
                    }
                    // 雙鍵同時按下 → 立即觸發 (移除 1.5 秒延遲)
                    if (isVolumeUpPressed && isVolumeDownPressed && accessibilityShortcutJob == null) {
                        accessibilityShortcutJob = lifecycleScope.launch {
                            if (isBlindMode) {
                                ttsManager.speak("已退出盲人模式")
                                viewModel.triggerCloseAccessibilityMode()
                            } else {
                                ttsManager.speak("已進入盲人模式")
                                viewModel.triggerAccessibilityMode()
                            }
                        }
                    }
                }
                android.view.KeyEvent.ACTION_UP -> {
                    when (keyCode) {
                        android.view.KeyEvent.KEYCODE_VOLUME_UP -> isVolumeUpPressed = false
                        android.view.KeyEvent.KEYCODE_VOLUME_DOWN -> isVolumeDownPressed = false
                    }
                    // 只要任一鍵放開，就取消標記，允許下一次點按觸發
                    accessibilityShortcutJob?.cancel()
                    accessibilityShortcutJob = null
                }
            }
        }

        // 不吃掉事件，讓系統照常處理音量
        return super.dispatchKeyEvent(event)
    }
}
