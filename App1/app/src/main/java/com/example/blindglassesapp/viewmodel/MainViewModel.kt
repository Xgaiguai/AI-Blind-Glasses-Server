package com.example.blindglassesapp.viewmodel

import android.app.Application
import android.bluetooth.BluetoothDevice
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.ble.BleManager
import com.example.blindglassesapp.network.EmergencyRepository
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** 緊急求助的狀態。 */
enum class EmergencyState {
    IDLE,    // 尚未觸發
    SENDING, // 發送中
    SENT,    // 已成功通知家屬
    FAILED   // 發送失敗
}

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val bleManager = BleManager(application)
    private val emergencyRepository = EmergencyRepository()

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

    // ── 緊急求助 ──
    private val _emergencyState = MutableStateFlow(EmergencyState.IDLE)
    val emergencyState: StateFlow<EmergencyState> = _emergencyState

    /**
     * 發送緊急求助到伺服器（伺服器會 LINE 推播家屬 + GPS 位置）。
     * UI 層可透過 [emergencyState] 觀察結果，提供 TTS 回饋。
     */
    fun sendEmergency() {
        if (_emergencyState.value == EmergencyState.SENDING) return // 防止重複發送
        _emergencyState.value = EmergencyState.SENDING
        viewModelScope.launch {
            val ok = emergencyRepository.sendEmergency()
            _emergencyState.value = if (ok) EmergencyState.SENT else EmergencyState.FAILED
        }
    }

    /** 重設緊急狀態為 IDLE（允許再次觸發）。 */
    fun resetEmergencyState() {
        _emergencyState.value = EmergencyState.IDLE
    }

    override fun onCleared() {
        super.onCleared()
        bleManager.release()
    }
}
