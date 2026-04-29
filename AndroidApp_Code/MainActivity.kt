package com.example.blindglassesapp

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.UUID
class MainActivity : ComponentActivity() {

    private val TAG = "BlindGlassesApp"

    private val SERVICE_UUID = UUID.fromString("6f2f6d30-4d57-4c76-a5dd-86f4d2a06340")
    private val WIFI_APPLY_CHAR_UUID = UUID.fromString("6f2f6d33-4d57-4c76-a5dd-86f4d2a06340")

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bluetoothLeScanner: BluetoothLeScanner? = null
    private var bluetoothGatt: BluetoothGatt? = null

    private var scanning = false
    private val handler = Handler(Looper.getMainLooper())
    
    // Scan period of 10 seconds.
    private val SCAN_PERIOD: Long = 10000

    private val deviceList = mutableListOf<BluetoothDevice>()

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        var allGranted = true
        permissions.entries.forEach {
            if (!it.value) {
                allGranted = false
            }
        }
        if (allGranted) {
            scanLeDevice()
        } else {
            Toast.makeText(this, "需要權限才能掃描藍牙", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bluetoothAdapter = bluetoothManager.adapter
        bluetoothLeScanner = bluetoothAdapter?.bluetoothLeScanner

        val scanButton = Button(this).apply {
            text = "掃描眼鏡"
            textSize = 24f
            setOnClickListener {
                checkPermissionsAndScan()
            }
        }

        val wifiButton = Button(this).apply {
            text = "設定網路"
            textSize = 24f
            setOnClickListener {
                showWifiSettingDialog()
            }
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(scanButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, 50) })
            
            addView(wifiButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ))
        }

        setContentView(layout)
    }

    private fun checkPermissionsAndScan() {
        val requiredPermissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        } else {
            arrayOf(
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        }

        val missingPermissions = requiredPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missingPermissions.isNotEmpty()) {
            requestPermissionLauncher.launch(missingPermissions.toTypedArray())
        } else {
            scanLeDevice()
        }
    }

    @SuppressLint("MissingPermission")
    private fun scanLeDevice() {
        if (bluetoothAdapter == null || bluetoothAdapter?.isEnabled == false) {
            val enableBtIntent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
            startActivity(enableBtIntent)
            return
        }
        
        // 確保重新取得 scanner (有時藍牙剛開啟時會是 null)
        if (bluetoothLeScanner == null) {
            bluetoothLeScanner = bluetoothAdapter?.bluetoothLeScanner
        }

        deviceList.clear()

        if (!scanning) {
            handler.postDelayed({
                scanning = false
                bluetoothLeScanner?.stopScan(leScanCallback)
                showDeviceSelectionDialog()
            }, SCAN_PERIOD)

            scanning = true
            bluetoothLeScanner?.startScan(leScanCallback)
            Toast.makeText(this, "開始掃描 BLE 裝置...", Toast.LENGTH_SHORT).show()
        } else {
            scanning = false
            bluetoothLeScanner?.stopScan(leScanCallback)
            showDeviceSelectionDialog()
        }
    }

    private val leScanCallback: ScanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            super.onScanResult(callbackType, result)
            val device = result.device
            // 避免重複加入
            if (!deviceList.any { it.address == device.address }) {
                // 可在此過濾設備名稱，例如 if (device.name?.contains("BlindGlasses") == true)
                deviceList.add(device)
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun showDeviceSelectionDialog() {
        if (deviceList.isEmpty()) {
            Toast.makeText(this, "未找到任何 BLE 裝置", Toast.LENGTH_SHORT).show()
            return
        }

        val deviceNames = deviceList.map { it.name ?: "Unknown Device (${it.address})" }.toTypedArray()

        AlertDialog.Builder(this)
            .setTitle("選擇導盲眼鏡")
            .setItems(deviceNames) { dialog, which ->
                val selectedDevice = deviceList[which]
                connectToDevice(selectedDevice)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    @SuppressLint("MissingPermission")
    private fun connectToDevice(device: BluetoothDevice) {
        Toast.makeText(this, "嘗試連線至 ${device.name ?: device.address}...", Toast.LENGTH_SHORT).show()
        // 斷開先前的連線
        bluetoothGatt?.close()
        bluetoothGatt = device.connectGatt(this, false, gattCallback)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                Log.i(TAG, "Connected to GATT server.")
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "連線成功！", Toast.LENGTH_SHORT).show()
                }
                // 發現服務
                gatt.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                Log.i(TAG, "Disconnected from GATT server.")
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "已斷開連線", Toast.LENGTH_SHORT).show()
                }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                Log.w(TAG, "onServicesDiscovered received: $status")
            } else {
                Log.w(TAG, "onServicesDiscovered received: $status")
            }
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt?,
            characteristic: android.bluetooth.BluetoothGattCharacteristic?,
            status: Int
        ) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "設定已成功傳送！", Toast.LENGTH_SHORT).show()
                }
            } else {
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "傳送失敗，請重試 (status=$status)", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun showWifiSettingDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(50, 40, 50, 10)
        }

        val ssidInput = EditText(this).apply {
            hint = "WiFi 名稱 (SSID)"
        }
        val pwdInput = EditText(this).apply {
            hint = "WiFi 密碼"
        }

        layout.addView(ssidInput)
        layout.addView(pwdInput)

        AlertDialog.Builder(this)
            .setTitle("設定網路")
            .setView(layout)
            .setPositiveButton("傳送") { dialog, _ ->
                val ssid = ssidInput.text.toString()
                val pwd = pwdInput.text.toString()
                
                if (bluetoothGatt != null) {
                    try {
                        val json = JSONObject()
                        json.put("ssid", ssid)
                        json.put("pwd", pwd)
                        json.put("wifiApply", 1)
                        
                        val payload = json.toString().toByteArray(Charsets.UTF_8)
                        
                        val service = bluetoothGatt?.getService(SERVICE_UUID)
                        if (service != null) {
                            val char = service.getCharacteristic(WIFI_APPLY_CHAR_UUID)
                            if (char != null) {
                                // 支援舊版與 API 32 以前的標準寫法
                                char.value = payload
                                val success = bluetoothGatt?.writeCharacteristic(char)
                                if (success != true) {
                                    Toast.makeText(this, "寫入請求失敗", Toast.LENGTH_SHORT).show()
                                }
                            } else {
                                Toast.makeText(this, "找不到對應的寫入特徵值", Toast.LENGTH_SHORT).show()
                            }
                        } else {
                            Toast.makeText(this, "找不到設定服務", Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                        Toast.makeText(this, "資料處理錯誤", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this, "請先連線導盲眼鏡！", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
}
