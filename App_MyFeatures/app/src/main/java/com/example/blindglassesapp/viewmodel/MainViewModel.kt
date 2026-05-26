package com.example.blindglassesapp.viewmodel

import android.app.Application
import android.bluetooth.BluetoothDevice
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.ble.BleManager
import com.example.blindglassesapp.data.UiThemeStorage
import com.example.blindglassesapp.data.WifiProfilesStorage
import com.example.blindglassesapp.ui.theme.AppThemePreference
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val bleManager = BleManager.getInstance(application)
    private val themeStorage = UiThemeStorage(application)
    private val wifiStorage = WifiProfilesStorage(application)

    val bleState: StateFlow<BleConnectionState> = bleManager.state

    val themePreference: StateFlow<AppThemePreference> = themeStorage.themeFlow

    private val _savedWifiProfiles = MutableStateFlow(wifiStorage.getSavedProfiles())
    val savedWifiProfiles: StateFlow<List<WifiProfilesStorage.WifiProfile>> = _savedWifiProfiles

    // 音量狀態，預設 15，範圍 0-21
    private val _currentVolume = MutableStateFlow(15)
    val currentVolume: StateFlow<Int> = _currentVolume

    sealed interface WifiWriteResult {
        object Success : WifiWriteResult
        data class Failure(val message: String) : WifiWriteResult
    }

    private val _wifiWriteResult = MutableStateFlow<WifiWriteResult?>(null)
    val wifiWriteResult: StateFlow<WifiWriteResult?> = _wifiWriteResult

    val isBluetoothEnabled: Boolean
        get() = bleManager.isBluetoothEnabled

    init {
        // 橋接 BleManager 的 writeResult 到 ViewModel 的 wifiWriteResult
        viewModelScope.launch {
            bleManager.writeResult.collect { result ->
                when (result) {
                    is BleManager.WriteResult.Success -> _wifiWriteResult.value = WifiWriteResult.Success
                    is BleManager.WriteResult.Failure -> _wifiWriteResult.value = WifiWriteResult.Failure(result.message)
                    null -> {}
                }
            }
        }
    }

    fun startScan() {
        bleManager.startScan()
    }

    fun connectDevice(device: BluetoothDevice) {
        bleManager.connect(device)
    }

    fun disconnect() {
        bleManager.disconnect()
    }

    fun dismissDeviceListResults() {
        bleManager.clearDevicesFoundState()
    }

    fun writeWifi(ssid: String, password: String) {
        val sent = bleManager.writeWifiCredentials(ssid, password)
        if (!sent) {
            _wifiWriteResult.value = WifiWriteResult.Failure("無法寫入 GATT 特徵，請確認眼鏡連線正常。")
        } else {
            // 預先存入歷史
            wifiStorage.saveProfile(ssid, password)
            _savedWifiProfiles.value = wifiStorage.getSavedProfiles()
        }
    }

    fun clearWriteResult() {
        _wifiWriteResult.value = null
        bleManager.clearWriteResult()
    }

    fun setTheme(pref: AppThemePreference) {
        themeStorage.setThemePreference(pref)
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



    override fun onCleared() {
        super.onCleared()
        bleManager.release()
    }
}
