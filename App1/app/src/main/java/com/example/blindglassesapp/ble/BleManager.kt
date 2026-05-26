package com.example.blindglassesapp.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject
import java.util.UUID

class BleManager(context: Context) {

    companion object {
        private const val TAG = "BleManager"
        private val SERVICE_UUID = UUID.fromString("6f2f6d30-4d57-4c76-a5dd-86f4d2a06340")
        private val WIFI_APPLY_CHAR_UUID = UUID.fromString("6f2f6d33-4d57-4c76-a5dd-86f4d2a06340")
        private val FIND_ME_UUID = UUID.fromString("6f2f6d34-4d57-4c76-a5dd-86f4d2a06340")
        private val VOLUME_UUID = UUID.fromString("6f2f6d37-4d57-4c76-a5dd-86f4d2a06340")
        private const val SCAN_PERIOD_MS = 10_000L
    }

    private val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val bluetoothAdapter: BluetoothAdapter? = bluetoothManager.adapter
    private var bluetoothGatt: BluetoothGatt? = null
    private val handler = Handler(Looper.getMainLooper())
    private val appContext = context.applicationContext

    private val _state = MutableStateFlow<BleConnectionState>(BleConnectionState.Idle)
    val state: StateFlow<BleConnectionState> = _state.asStateFlow()

    private val _writeResult = MutableStateFlow<WriteResult?>(null)
    val writeResult: StateFlow<WriteResult?> = _writeResult.asStateFlow()

    private val foundDevices = mutableListOf<BluetoothDevice>()

    val isBluetoothSupported: Boolean
        get() = bluetoothAdapter != null

    val isBluetoothEnabled: Boolean
        get() = bluetoothAdapter?.isEnabled == true

    private val scanSettings =
        ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

    // --- Scan ---

    /**
     * 開始 LE 掃描（不套用 `ScanFilter`），附近可見的 BLE 裝置皆可能出現在清單。
     * UI 會優先列出有廣播名稱的裝置；眼鏡若廣播名稱被省略，請改以 MAC 辨識。
     * 連線後 Wi‑Fi 寫入仍須裝置提供 GATT 服務 `6f2f6d30-4d57-4c76-a5dd-86f4d2a06340`（韌體 `BLE_QUICK_LINK_ENABLE=1` 才會廣播／啟用 GATT）。
     */
    @SuppressLint("MissingPermission")
    fun startScan() {
        val scanner = bluetoothAdapter?.bluetoothLeScanner
        if (scanner == null) {
            _state.value = BleConnectionState.Error("藍牙不可用")
            return
        }

        foundDevices.clear()
        _state.value = BleConnectionState.Scanning

        handler.postDelayed({
            scanner.stopScan(scanCallback)
            if (foundDevices.isEmpty()) {
                _state.value = BleConnectionState.Error("未找到任何 BLE 裝置")
            } else {
                _state.value = BleConnectionState.DevicesFound(foundDevices.toList())
            }
        }, SCAN_PERIOD_MS)

        scanner.startScan(null, scanSettings, scanCallback)
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        bluetoothAdapter?.bluetoothLeScanner?.stopScan(scanCallback)
        handler.removeCallbacksAndMessages(null)
    }

    /** 掃描結果仍為 [BleConnectionState.DevicesFound] 時，關閉清單或進入其他頁面前呼叫，避免返回首頁再次自動彈出清單。 */
    fun clearDevicesFoundState() {
        if (_state.value is BleConnectionState.DevicesFound) {
            _state.value = BleConnectionState.Idle
        }
    }

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            if (foundDevices.none { it.address == device.address }) {
                foundDevices.add(device)
            }
        }
    }

    // --- Connect ---

    @SuppressLint("MissingPermission")
    fun connect(device: BluetoothDevice) {
        stopScan()
        // 先清目前 GATT 參考再 close，否則舊連線晚到的 DISCONNECTED 會覆寫「連線中／已連線」狀態。
        val oldGatt = bluetoothGatt
        bluetoothGatt = null
        oldGatt?.close()
        val name = device.name ?: device.address
        _state.value = BleConnectionState.Connecting(name)
        bluetoothGatt =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(appContext, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            } else {
                @Suppress("DEPRECATION")
                device.connectGatt(appContext, false, gattCallback)
            }
    }

    @SuppressLint("MissingPermission")
    fun disconnect() {
        val g = bluetoothGatt
        bluetoothGatt = null
        g?.close()
        _state.value = BleConnectionState.Disconnected
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (gatt != bluetoothGatt) {
                Log.w(TAG, "Ignoring stale GATT state change (session replaced): status=$status newState=$newState")
                return
            }
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    if (status != BluetoothGatt.GATT_SUCCESS) {
                        Log.e(TAG, "STATE_CONNECTED but status=$status (stack may disconnect)")
                    }
                    Log.i(TAG, "Connected to GATT server, status=$status")
                    gatt.discoverServices()
                    val name = gatt.device?.name ?: gatt.device?.address ?: "裝置"
                    _state.value = BleConnectionState.Connected(name)
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from GATT server, status=$status")
                    if (bluetoothGatt == gatt) {
                        bluetoothGatt = null
                    }
                    gatt.close()
                    _state.value = BleConnectionState.Disconnected
                }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            Log.d(TAG, "onServicesDiscovered status=$status")
            if (status == BluetoothGatt.GATT_SUCCESS &&
                gatt == bluetoothGatt &&
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP
            ) {
                // 觸發 MTU 交握，否則對端 status notify 僅 20 bytes（預設 ATT MTU 23）。
                @SuppressLint("MissingPermission")
                val ok = gatt.requestMtu(517)
                Log.d(TAG, "requestMtu(517) queued=$ok")
            }
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            Log.d(TAG, "onMtuChanged mtu=$mtu status=$status")
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt?,
            characteristic: BluetoothGattCharacteristic?,
            status: Int
        ) {
            _writeResult.value = if (status == BluetoothGatt.GATT_SUCCESS) {
                WriteResult.Success
            } else {
                WriteResult.Failure("寫入失敗 (status=$status)")
            }
        }
    }

    // --- WiFi Write ---

    @SuppressLint("MissingPermission")
    fun writeWifiCredentials(ssid: String, password: String): Boolean {
        val gatt = bluetoothGatt ?: return false
        val service = gatt.getService(SERVICE_UUID) ?: return false
        val char = service.getCharacteristic(WIFI_APPLY_CHAR_UUID) ?: return false

        val json = JSONObject().apply {
            put("ssid", ssid)
            put("pwd", password)
            put("wifiApply", 1)
        }
        val payload = json.toString().toByteArray(Charsets.UTF_8)

        _writeResult.value = null
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            gatt.writeCharacteristic(char, payload, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
        } else {
            @Suppress("DEPRECATION")
            char.value = payload
            @Suppress("DEPRECATION")
            gatt.writeCharacteristic(char)
        }
    }

    @SuppressLint("MissingPermission")
    fun writeFindMe(): Boolean {
        val gatt = bluetoothGatt ?: return false
        val service = gatt.getService(SERVICE_UUID) ?: return false
        val char = service.getCharacteristic(FIND_ME_UUID) ?: return false

        val payload = "1".toByteArray(Charsets.UTF_8)

        _writeResult.value = null
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            gatt.writeCharacteristic(char, payload, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
        } else {
            @Suppress("DEPRECATION")
            char.value = payload
            @Suppress("DEPRECATION")
            gatt.writeCharacteristic(char)
        }
    }

    @SuppressLint("MissingPermission")
    fun writeVolume(volume: Int): Boolean {
        val vol = volume.coerceIn(0, 21)
        val gatt = bluetoothGatt ?: return false
        val service = gatt.getService(SERVICE_UUID) ?: return false
        val char = service.getCharacteristic(VOLUME_UUID) ?: return false

        val payload = vol.toString().toByteArray(Charsets.UTF_8)

        _writeResult.value = null
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            gatt.writeCharacteristic(char, payload, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
        } else {
            @Suppress("DEPRECATION")
            char.value = payload
            @Suppress("DEPRECATION")
            gatt.writeCharacteristic(char)
        }
    }

    fun clearWriteResult() {
        _writeResult.value = null
    }

    fun release() {
        stopScan()
        disconnect()
    }

    sealed class WriteResult {
        data object Success : WriteResult()
        data class Failure(val message: String) : WriteResult()
    }
}
