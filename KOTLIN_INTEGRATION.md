# Guía de Integración Kotlin - PetPal API

Esta guía contiene las clases de datos y la interfaz de Retrofit necesaria para conectar la aplicación Android con el backend de FastAPI.

## 1. Dependencias Necesarias (build.gradle)
```kotlin
implementation("com.squareup.retrofit2:retrofit:2.9.0")
implementation("com.squareup.retrofit2:converter-gson:2.9.0")
implementation("com.squareup.okhttp3:logging-interceptor:4.9.1")
```

## 2. Modelos de Datos (Data Classes)

```kotlin
data class TokenResponse(
    val access_token: String,
    val token_type: String
)

data class User(
    val id: Int,
    val email: String,
    val full_name: String,
    val phone: String,
    val role: String,
    val status: String
)

data class UserCreate(
    val email: String,
    val full_name: String,
    val phone: String,
    val password: String
)

data class Pet(
    val id: Int,
    val owner_id: Int,
    val name: String,
    val species: String,
    val breed: String,
    val birth_date: String,
    val weight: Float,
    val photo_url: String?
)

data class PetCreate(
    val name: String,
    val species: String,
    val breed: String,
    val birth_date: String,
    val weight: Float,
    val photo_url: String? = null
)

data class Appointment(
    val id: Int,
    val pet_id: Int,
    val owner_id: Int,
    val date_time: String, // Formato ISO: "2023-10-27T10:00:00"
    val reason: String,
    val status: String
)

data class AppointmentCreate(
    val pet_id: Int,
    val date_time: String,
    val reason: String
)

data class MedicalRecord(
    val id: Int,
    val pet_id: Int,
    val date: String,
    val diagnosis: String,
    val treatment: String,
    val notes: String
)
```

## 3. Interfaz de API (Retrofit)

```kotlin
interface PetPalApiService {

    // --- Autenticación ---
    @POST("auth/register")
    suspend fun register(@Body user: UserCreate): User

    @FormUrlEncoded
    @POST("auth/login")
    suspend fun login(
        @Field("username") email: String,
        @Field("password") pass: String
    ): TokenResponse

    @GET("users/me")
    suspend fun getMyProfile(@Header("Authorization") token: String): User

    // --- Mascotas ---
    @GET("pets/")
    suspend fun getMyPets(@Header("Authorization") token: String): List<Pet>

    @POST("pets/")
    suspend fun createPet(
        @Header("Authorization") token: String,
        @Body pet: PetCreate
    ): Pet

    @GET("pets/{id}/history")
    suspend fun getPetHistory(
        @Header("Authorization") token: String,
        @Path("id") petId: Int
    ): List<MedicalRecord>

    // --- Citas ---
    @GET("appointments/me")
    suspend fun getMyAppointments(@Header("Authorization") token: String): List<Appointment>

    @POST("appointments/")
    suspend fun createAppointment(
        @Header("Authorization") token: String,
        @Body appointment: AppointmentCreate
    ): Appointment

    // --- Admin ---
    @GET("admin/users/pending")
    suspend fun getPendingUsers(@Header("Authorization") token: String): List<User>

    @PATCH("admin/users/{id}/approve")
    suspend fun approveUser(
        @Header("Authorization") token: String,
        @Path("id") userId: Int
    ): User
}
```

## 4. Notas Importantes para el Frontend
1. **Manejo de Errores:** Cuando el login falla porque el usuario está pendiente, la API devuelve un código **403 Forbidden**. Deben capturar esto para mostrar la pantalla de "Espera de aprobación".
2. **Tokens:** El token debe enviarse en el header como `Authorization: Bearer <tu_token>`.
3. **URL Base:** Si usan el emulador de Android, la URL base para conectar con su PC suele ser `http://10.0.2.2:8000/`.
