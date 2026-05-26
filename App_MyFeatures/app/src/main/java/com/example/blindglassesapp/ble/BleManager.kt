package com.example.blindglassesapp.ble

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.UUID

@SuppressLint("MissingPermission")
class BleManager private constructor(private val context: Context) {

    companion object {
        private const val TAG = "BleManager"
        private const val SCAN_PERIOD = 8000L // 掃描 8 秒

        // ── Wi-Fi 設定服務（舊版，保留現有功能） ──────────────────────────────
        private val SERVICE_UUID = UUID.fromString("4fafc201-1fb5-459e-8fcc-c5c9c331914b")
        private val CHARACTERISTIC_UUID = UUID.fromString("beb5483e-36e1-4688-b7f5-ea07361b26a8")

        // ── BLE Quick Link 服務（音量 / 找眼鏡） ─────────────────────────────
        private val QUICK_LINK_SERVICE_UUID = UUID.fromString("6f2f6d30-4d57-4c76-a5dd-86f4d2a06340")
        private val FIND_ME_UUID            = UUID.fromString("6f2f6d34-4d57-4c76-a5dd-86f4d2a06340")
        private val VOLUME_UUID             = UUID.fromString("6f2f6d37-4d57-4c76-a5dd-86f4d2a06340")

        @SuppressLint("StaticFieldLeak")
        @Volatile
        private var INSTANCE: BleManager? = null

        fun getInstance(context: Context): BleManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: BleManager(context.applicationContext).also { INSTANCE = it }
            }
        }
    }

    private val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val bluetoothAdapter = bluetoothManager.adapter
    private val mainHandler = Handler(Looper.getMainLooper())

    private val _state = MutableStateFlow<BleConnectionState>(BleConnectionState.Idle)
    val state: StateFlow<BleConnectionState> = _state

    private val _writeResult = MutableStateFlow<WriteResult?>(null)
    val writeResult: StateFlow<WriteResult?> = _writeResult

    sealed interface WriteResult {
        object Success : WriteResult
        data class Failure(val message: String) : WriteResult
    }

    private val foundDevices = mutableListOf<BluetoothDevice>()
    private var bluetoothGatt: BluetoothGatt? = null
    private var isScanning = false

    // Quick Link 特徵，連線後探索取得
    private var findMeCharacteristic: android.bluetooth.BluetoothGattCharacteristic? = null
    private var volumeCharacteristic: android.bluetooth.BluetoothGattCharacteristic? = null

    val isBluetoothEnabled: Boolean
        get() = bluetoothAdapter?.isEnabled == true

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            if (device.name != null && !foundDevices.any { it.address == device.address }) {
                foundDevices.add(device)
                Log.d(TAG, "發現裝置: ${device.name} (${device.address})")
            }
        }
    }

    fun startScan() {
        if (!isBluetoothEnabled) return
        if (isScanning) return

        foundDevices.clear()
        isScanning = true
        _state.value = BleConnectionState.Scanning

        mainHandler.postDelayed({
            if (isScanning) {
                stopScan()
            }
        }, SCAN_PERIOD)

        bluetoothAdapter.bluetoothLeScanner?.startScan(scanCallback)
    }

    fun stopScan() {
        if (!isScanning) return
        isScanning = false
        bluetoothAdapter.bluetoothLeScanner?.stopScan(scanCallback)
        _state.value = BleConnectionState.ScanFinished(ArrayList(foundDevices))
    }

    fun clearDevicesFoundState() {
        if (_state.value is BleConnectionState.ScanFinished) {
            _state.value = BleConnectionState.Idle
        }
    }

    fun connect(device: BluetoothDevice) {
        stopScan()
        _state.value = BleConnectionState.Connecting
        bluetoothGatt = device.connectGatt(context, false, gattCallback)
    }

    fun disconnect() {
        bluetoothGatt?.disconnect()
    }

    fun clearWriteResult() {
        _writeResult.value = null
    }

    fun writeWifiCredentials(ssid: String, password: String): Boolean {
        val gatt = bluetoothGatt ?: return false
        val service = gatt.getService(SERVICE_UUID) ?: return false
        val characteristic = service.getCharacteristic(CHARACTERISTIC_UUID) ?: return false

        val payload = "$ssid,$password"
        characteristic.value = payload.toByteArray(Charsets.UTF_8)
        characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        return gatt.writeCharacteristic(characteristic)
    }

    /**
     * 觸發「找眼鏡」功能：眼鏡會播放提示聲。
     * 需已連線至 Quick Link 服務。
     */
    fun writeFindMe(): Boolean {
        val gatt = bluetoothGatt ?: return false
        val characteristic = findMeCharacteristic ?: return false
        characteristic.value = "1".toByteArray(Charsets.UTF_8)
        characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        return gatt.writeCharacteristic(characteristic)
    }

    /**
     * 設定眼鏡音量。
     * @param volume 音量值，範圍 0-21。
     */
    fun writeVolume(volume: Int): Boolean {
        val vol = volume.coerceIn(0, 21)
        val gatt = bluetoothGatt ?: return false
        val characteristic = volumeCharacteristic ?: return false
        characteristic.value = vol.toString().toByteArray(Charsets.UTF_8)
        characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        return gatt.writeCharacteristic(characteristic)
    }

    fun release() {
        disconnect()
        bluetoothGatt?.close()
        bluetoothGatt = null
        findMeCharacteristic = null
        volumeCharacteristic = null
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    Log.d(TAG, "已連線，開始探索服務...")
                    gatt.discoverServices()
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    Log.d(TAG, "已中斷連線")
                    _state.value = BleConnectionState.Disconnected("Device disconnected")
                    gatt.close()
                    bluetoothGatt = null
                }
            } else {
                Log.e(TAG, "GATT 異常狀態碼: $status")
                _state.value = BleConnectionState.Disconnected("Error code: $status")
                gatt.close()
                bluetoothGatt = null
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                // ── 探索 Wi-Fi 設定服務（必要） ──────────────────────────────────
                val wifiService = gatt.getService(SERVICE_UUID)
                val wifiCharacteristic = wifiService?.getCharacteristic(CHARACTERISTIC_UUID)

                // ── 探索 Quick Link 服務（選用：音量 / 找眼鏡） ─────────────────
                val quickLinkService = gatt.getService(QUICK_LINK_SERVICE_UUID)
                if (quickLinkService != null) {
                    findMeCharacteristic = quickLinkService.getCharacteristic(FIND_ME_UUID)
                    volumeCharacteristic  = quickLinkService.getCharacteristic(VOLUME_UUID)
                    Log.d(TAG, "Quick Link 服務已探索：FindMe=${findMeCharacteristic != null}, Volume=${volumeCharacteristic != null}")
                } else {
                    Log.w(TAG, "Quick Link 服務未找到（FindMe / Volume 功能不可用）")
                }

                if (wifiCharacteristic != null) {
                    Log.d(TAG, "連線成功且服務特徵探索完畢")
                    _state.value = BleConnectionState.Connected(gatt.device)
                } else {
                    Log.e(TAG, "探索成功，但找不到指定的 ESP32 Wi-Fi 服務或特徵")
                    _state.value = BleConnectionState.Disconnected("ESP32 target service not found")
                    gatt.disconnect()
                }
            } else {
                _state.value = BleConnectionState.Disconnected("Service discovery failed")
                gatt.disconnect()
            }
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            status: Int
        ) {
            if (characteristic.uuid == CHARACTERISTIC_UUID) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    Log.d(TAG, "Wi-Fi 憑證寫入成功")
                    _writeResult.value = WriteResult.Success
                } else {
                    Log.e(TAG, "Wi-Fi 憑證寫入失敗 status: $status")
                    _writeResult.value = WriteResult.Failure("Error code: $status")
                }
            }
        }
    }
}
