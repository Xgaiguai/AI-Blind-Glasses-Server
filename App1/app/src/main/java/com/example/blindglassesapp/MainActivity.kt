package com.example.blindglassesapp

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
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
    private val WIFI_SSID_CHAR_UUID = UUID.fromString("6f2f6d31-4d57-4c76-a5dd-86f4d2a06340")
    private val WIFI_PASS_CHAR_UUID = UUID.fromString("6f2f6d32-4d57-4c76-a5dd-86f4d2a06340")
    private val WIFI_APPLY_CHAR_UUID = UUID.fromString("6f2f6d33-4d57-4c76-a5dd-86f4d2a06340")
    private val MODE_CHAR_UUID = UUID.fromString("6f2f6d36-4d57-4c76-a5dd-86f4d2a06340")
    private val VOLUME_CHAR_UUID = UUID.fromString("6f2f6d37-4d57-4c76-a5dd-86f4d2a06340")

    private val STATUS_CHAR_UUID = UUID.fromString("6f2f6d35-4d57-4c76-a5dd-86f4d2a06340")
    private val FIND_ME_CHAR_UUID = UUID.fromString("6f2f6d34-4d57-4c76-a5dd-86f4d2a06340")

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bluetoothLeScanner: BluetoothLeScanner? = null
    private var bluetoothGatt: BluetoothGatt? = null

    // UI Elements for Status
    private lateinit var batteryStatusText: android.widget.TextView
    private lateinit var wifiStatusText: android.widget.TextView
    private lateinit var connectionStatusText: android.widget.TextView

    private var scanning = false
    private var lastEsp32Ip: String? = null
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

        // --- Status Dashboard ---
        val statusCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
            setBackgroundResource(android.R.drawable.dialog_holo_light_frame)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(20, 20, 20, 40) }
        }

        connectionStatusText = android.widget.TextView(this).apply {
            text = "連線狀態: 未連線"
            textSize = 18f
            setTextColor(android.graphics.Color.RED)
            setPadding(0, 0, 0, 10)
        }

        batteryStatusText = android.widget.TextView(this).apply {
            text = "電量: --%"
            textSize = 16f
            setPadding(0, 5, 0, 5)
        }

        wifiStatusText = android.widget.TextView(this).apply {
            text = "網路: 未知"
            textSize = 16f
            setPadding(0, 5, 0, 5)
        }

        statusCard.addView(connectionStatusText)
        statusCard.addView(batteryStatusText)
        statusCard.addView(wifiStatusText)

        val liveViewButton = Button(this).apply {
            text = "查看即時畫面"
            textSize = 24f
            setOnClickListener {
                if (!lastEsp32Ip.isNullOrEmpty() && lastEsp32Ip != "0.0.0.0") {
                    val url = "http://$lastEsp32Ip:81/stream"
                    val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))
                    startActivity(intent)
                } else {
                    Toast.makeText(this@MainActivity, "尚未取得眼鏡 IP，請確認眼鏡已連上 WiFi", Toast.LENGTH_SHORT).show()
                }
            }
        }

        val scanButton = Button(this).apply {
            text = "連接眼鏡藍芽"
            textSize = 24f
            setOnClickListener {
                checkPermissionsAndScan()
            }
        }

        val wifiButton = Button(this).apply {
            text = "設定眼鏡網路"
            textSize = 24f
            setOnClickListener {
                val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
                startActivity(intent)
            }
        }

        val modeButton = Button(this).apply {
            text = "設定眼鏡模式"
            textSize = 24f
            setOnClickListener {
                showModeSettingDialog()
            }
        }

        val volumeButton = Button(this).apply {
            text = "設定眼鏡音量"
            textSize = 24f
            setOnClickListener {
                showVolumeSettingDialog()
            }
        }

        val findMeButton = Button(this).apply {
            text = "尋找眼鏡 (發出聲響)"
            textSize = 24f
            setTextColor(android.graphics.Color.WHITE)
            setBackgroundColor(android.graphics.Color.parseColor("#FF9800")) // 橘色醒目
            setOnClickListener {
                sendFindMeRequest()
            }
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            
            // 增加上方 padding 避免被手機狀態列 (時間、電量) 遮擋
            val density = resources.displayMetrics.density
            val topPadding = (60 * density).toInt() 
            setPadding(20, topPadding, 20, 40)
            
            addView(statusCard)
            addView(liveViewButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 50) })
            
            addView(scanButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 50) })

            addView(wifiButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 50) })

            addView(modeButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 50) })

            addView(volumeButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 50) })

            addView(findMeButton, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 30, 40, 50) })
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
                    connectionStatusText.text = "連線狀態: 已連線"
                    connectionStatusText.setTextColor(android.graphics.Color.parseColor("#4CAF50"))
                }
                // 發現服務
                gatt.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                Log.i(TAG, "Disconnected from GATT server.")
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "已斷開連線", Toast.LENGTH_SHORT).show()
                    connectionStatusText.text = "連線狀態: 未連線"
                    connectionStatusText.setTextColor(android.graphics.Color.RED)
                    batteryStatusText.text = "電量: --%"
                    wifiStatusText.text = "網路: 未知"
                }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                Log.w(TAG, "onServicesDiscovered success")
                enableStatusNotification(gatt)
            } else {
                Log.w(TAG, "onServicesDiscovered received: $status")
            }
        }

        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: android.bluetooth.BluetoothGattCharacteristic
        ) {
            if (characteristic.uuid == STATUS_CHAR_UUID) {
                val data = characteristic.value
                if (data != null) {
                    val jsonStr = String(data, Charsets.UTF_8)
                    updateStatusUI(jsonStr)
                }
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
    private fun enableStatusNotification(gatt: BluetoothGatt) {
        val service = gatt.getService(SERVICE_UUID)
        val characteristic = service?.getCharacteristic(STATUS_CHAR_UUID)
        if (characteristic != null) {
            gatt.setCharacteristicNotification(characteristic, true)
            val descriptor = characteristic.getDescriptor(
                UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
            )
            descriptor?.let {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    gatt.writeDescriptor(it, android.bluetooth.BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    it.value = android.bluetooth.BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    gatt.writeDescriptor(it)
                }
            }
            Log.i(TAG, "Status notification enabled")
        }
    }

    private fun updateStatusUI(jsonStr: String) {
        try {
            val json = JSONObject(jsonStr)
            val wifiConnected = json.optBoolean("wifi", false)
            val ssid = json.optString("ssid", "Unknown")
            val battery = json.optInt("battery", -1)
            val ip = json.optString("ip", "")

            runOnUiThread {
                if (ip.isNotEmpty() && ip != "0.0.0.0") {
                    lastEsp32Ip = ip
                }
                batteryStatusText.text = if (battery >= 0) "電量: $battery%" else "電量: 尚未回報"
                wifiStatusText.text = if (wifiConnected) "網路: 已連線 ($ssid)\nIP: ${lastEsp32Ip ?: "取得中"}" else "網路: 未連線"
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing status JSON: ${e.message}")
        }
    }



    @SuppressLint("MissingPermission")
    private fun showModeSettingDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(50, 40, 50, 10)
        }

        val opModeTitle = android.widget.TextView(this).apply {
            text = "操作模式 (OpMode)"
            textSize = 18f
            setPadding(0, 0, 0, 10)
        }
        val opModeGroup = android.widget.RadioGroup(this)
        val btnSingle = android.widget.RadioButton(this).apply { 
            text = "單次按鈕 (SINGLE_BTN)"
            tag = "SINGLE_BTN" 
        }
        val btnAlways = android.widget.RadioButton(this).apply { 
            text = "持續運作 (ALWAYS_ON)"
            tag = "ALWAYS_ON" 
        }
        opModeGroup.addView(btnSingle)
        opModeGroup.addView(btnAlways)
        btnSingle.isChecked = true // 預設

        val taskModeTitle = android.widget.TextView(this).apply {
            text = "任務模式 (Task Mode)"
            textSize = 18f
            setPadding(0, 30, 0, 10)
        }
        val taskModeGroup = android.widget.RadioGroup(this)
        val btnGeneral = android.widget.RadioButton(this).apply { 
            text = "一般辨識 (general)"
            tag = "general" 
        }
        val btnLight = android.widget.RadioButton(this).apply { 
            text = "尋光模式 (light)"
            tag = "light" 
        }
        val btnItem = android.widget.RadioButton(this).apply { 
            text = "物品尋找 (item_search)"
            tag = "item_search" 
        }
        taskModeGroup.addView(btnGeneral)
        taskModeGroup.addView(btnLight)
        taskModeGroup.addView(btnItem)
        btnGeneral.isChecked = true // 預設

        layout.addView(opModeTitle)
        layout.addView(opModeGroup)
        layout.addView(taskModeTitle)
        layout.addView(taskModeGroup)

        AlertDialog.Builder(this)
            .setTitle("設定模式")
            .setView(layout)
            .setPositiveButton("傳送") { _, _ ->
                val opId = opModeGroup.checkedRadioButtonId
                val opTag = opModeGroup.findViewById<android.widget.RadioButton>(opId)?.tag?.toString() ?: "SINGLE_BTN"
                
                val taskId = taskModeGroup.checkedRadioButtonId
                val taskTag = taskModeGroup.findViewById<android.widget.RadioButton>(taskId)?.tag?.toString() ?: "general"

                sendModeToDevice(opTag, taskTag)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    @SuppressLint("MissingPermission")
    private fun sendModeToDevice(opMode: String, taskMode: String) {
        if (bluetoothGatt == null) {
            Toast.makeText(this, "請先連線導盲眼鏡！", Toast.LENGTH_SHORT).show()
            return
        }

        try {
            val json = JSONObject()
            // 這裡使用的 key ("op_mode", "task_mode") 需與韌體端解析的 JSON 一致
            json.put("op_mode", opMode)
            json.put("task_mode", taskMode)

            val payload = json.toString().toByteArray(Charsets.UTF_8)

            val service = bluetoothGatt?.getService(SERVICE_UUID)
            if (service != null) {
                val char = service.getCharacteristic(MODE_CHAR_UUID)
                if (char != null) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        val status = bluetoothGatt?.writeCharacteristic(
                            char,
                            payload,
                            android.bluetooth.BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                        )
                        if (status != android.bluetooth.BluetoothStatusCodes.SUCCESS) {
                            Toast.makeText(this, "寫入模式失敗", Toast.LENGTH_SHORT).show()
                        }
                    } else {
                        @Suppress("DEPRECATION")
                        char.value = payload
                        @Suppress("DEPRECATION")
                        val success = bluetoothGatt?.writeCharacteristic(char)
                        if (success != true) {
                            Toast.makeText(this, "寫入模式失敗", Toast.LENGTH_SHORT).show()
                        }
                    }
                } else {
                    Toast.makeText(this, "找不到寫入特徵值", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "找不到藍牙服務", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(this, "資料處理錯誤", Toast.LENGTH_SHORT).show()
        }
    }

    @SuppressLint("MissingPermission")
    private fun showVolumeSettingDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(50, 40, 50, 10)
        }

        val volumeTitle = android.widget.TextView(this).apply {
            text = "語音音量 (0-21)"
            textSize = 18f
            setPadding(0, 0, 0, 10)
        }
        
        val seekBar = android.widget.SeekBar(this).apply {
            max = 21
            progress = 15 // 預設值
        }
        
        val volumeText = android.widget.TextView(this).apply {
            text = "目前音量: 15"
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(0, 20, 0, 0)
        }

        seekBar.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                volumeText.text = "目前音量: $progress"
            }
            override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
        })

        layout.addView(volumeTitle)
        layout.addView(seekBar)
        layout.addView(volumeText)

        AlertDialog.Builder(this)
            .setTitle("設定音量")
            .setView(layout)
            .setPositiveButton("傳送") { _, _ ->
                val volume = seekBar.progress
                sendVolumeToDevice(volume)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    @SuppressLint("MissingPermission")
    private fun sendVolumeToDevice(volume: Int) {
        if (bluetoothGatt == null) {
            Toast.makeText(this, "請先連線導盲眼鏡！", Toast.LENGTH_SHORT).show()
            return
        }

        try {
            // 將音量轉成字串 ByteArray 送出，韌體端收到字串後會轉為數字
            val payload = volume.toString().toByteArray(Charsets.UTF_8)

            val service = bluetoothGatt?.getService(SERVICE_UUID)
            if (service != null) {
                val char = service.getCharacteristic(VOLUME_CHAR_UUID)
                if (char != null) {
                    writeBleData(char, payload)
                    // writeBleData 內會執行傳送，這裡直接給予提示
                } else {
                    Toast.makeText(this, "找不到音量特徵值，請確認韌體已更新", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "找不到藍牙服務", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(this, "資料處理錯誤", Toast.LENGTH_SHORT).show()
        }
    }

    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    private fun writeBleData(
        char: android.bluetooth.BluetoothGattCharacteristic,
        payload: ByteArray
    ) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            bluetoothGatt?.writeCharacteristic(
                char,
                payload,
                android.bluetooth.BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            )
        } else {
            char.value = payload
            bluetoothGatt?.writeCharacteristic(char)
        }
    }
    @SuppressLint("MissingPermission")
    private fun sendFindMeRequest() {
        if (bluetoothGatt == null) {
            Toast.makeText(this, "請先連線導盲眼鏡！", Toast.LENGTH_SHORT).show()
            return
        }

        try {
            val payload = "1".toByteArray(Charsets.UTF_8)
            val service = bluetoothGatt?.getService(SERVICE_UUID)
            if (service != null) {
                val char = service.getCharacteristic(FIND_ME_CHAR_UUID)
                if (char != null) {
                    writeBleData(char, payload)
                    Toast.makeText(this, "已發送尋找眼鏡請求", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "找不到尋找眼鏡特徵值", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "找不到藍牙服務", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(this, "資料處理錯誤", Toast.LENGTH_SHORT).show()
        }
    }
}
