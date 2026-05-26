package com.example.blindglassesapp.ble

import android.bluetooth.BluetoothDevice

sealed class BleConnectionState {
    data object Idle : BleConnectionState()
    data object Scanning : BleConnectionState()
    data class DevicesFound(val devices: List<BluetoothDevice>) : BleConnectionState()
    data class Connecting(val deviceName: String) : BleConnectionState()
    data class Connected(val deviceName: String) : BleConnectionState()
    data class Error(val message: String) : BleConnectionState()
    data object Disconnected : BleConnectionState()
}
