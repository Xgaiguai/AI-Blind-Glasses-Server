package com.example.blindglassesapp.viewmodel

import android.app.Application
import android.bluetooth.BluetoothDevice
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.ble.BleManager
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val bleManager = BleManager(application)

    val bleState: StateFlow<BleConnectionState> = bleManager.state
    val writeResult: StateFlow<BleManager.WriteResult?> = bleManager.writeResult

    val isBluetoothSupported: Boolean
        get() = bleManager.isBluetoothSupported

    val isBluetoothEnabled: Boolean
        get() = bleManager.isBluetoothEnabled

    val isConnected: Boolean
        get() = bleState.value is BleConnectionState.Connected

    fun startScan() = bleManager.startScan()

    fun stopScan() = bleManager.stopScan()

    fun connectDevice(device: BluetoothDevice) = bleManager.connect(device)

    fun disconnect() = bleManager.disconnect()

    /** 清除「掃描完成、裝置清單」狀態，使返回首頁時不會再自動打開底部表。 */
    fun dismissDeviceListResults() = bleManager.clearDevicesFoundState()

    fun writeWifiCredentials(ssid: String, password: String): Boolean {
        return bleManager.writeWifiCredentials(ssid, password)
    }

    fun clearWriteResult() = bleManager.clearWriteResult()

    // 音量狀態，預設 15，範圍 0-21
    private val _currentVolume = kotlinx.coroutines.flow.MutableStateFlow(15)
    val currentVolume: StateFlow<Int> = _currentVolume

    // 是否正在音量調整模式（直接透過手機實體音量鍵調整眼鏡音量）
    private val _isVolumeAdjustmentActive = kotlinx.coroutines.flow.MutableStateFlow(false)
    val isVolumeAdjustmentActive: StateFlow<Boolean> = _isVolumeAdjustmentActive

    fun setVolumeAdjustmentActive(active: Boolean) {
        _isVolumeAdjustmentActive.value = active
    }

    /**
     * 觸發找眼鏡，眼鏡會播放提示聲。
     * @return true = BLE 寫入指令已發送。
     */
    fun sendFindMe(): Boolean {
        return bleManager.writeFindMe()
    }

    /**
     * 音量加一（1 階），上限 21。
     * @return true = BLE 寫入指令已發送。
     */
    fun increaseVolume(): Boolean {
        val next = (_currentVolume.value + 1).coerceAtMost(21)
        val sent = bleManager.writeVolume(next)
        if (sent) _currentVolume.value = next
        return sent
    }

    /**
     * 音量減一（1 階），下限 0。
     * @return true = BLE 寫入指令已發送。
     */
    fun decreaseVolume(): Boolean {
        val next = (_currentVolume.value - 1).coerceAtLeast(0)
        val sent = bleManager.writeVolume(next)
        if (sent) _currentVolume.value = next
        return sent
    }

    // ── 盲人模式狀態與事件 ──
    private val _isAccessibilityModeActive = kotlinx.coroutines.flow.MutableStateFlow(false)
    val isAccessibilityModeActive: StateFlow<Boolean> = _isAccessibilityModeActive

    fun setAccessibilityModeActive(active: Boolean) {
        _isAccessibilityModeActive.value = active
    }

    private val _openAccessibilityEvent = MutableSharedFlow<Unit>()
    val openAccessibilityEvent: SharedFlow<Unit> = _openAccessibilityEvent

    fun triggerAccessibilityMode() {
        viewModelScope.launch { _openAccessibilityEvent.emit(Unit) }
    }

    private val _closeAccessibilityEvent = MutableSharedFlow<Unit>()
    val closeAccessibilityEvent: SharedFlow<Unit> = _closeAccessibilityEvent

    fun triggerCloseAccessibilityMode() {
        viewModelScope.launch { _closeAccessibilityEvent.emit(Unit) }
    }

    override fun onCleared() {
        super.onCleared()
        bleManager.release()
    }
}
