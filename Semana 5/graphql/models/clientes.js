const mongoose = require('mongoose');
const clienteSchema = mongoose.Schema({
    nombre: String,
    pass: String
});

module.exports = mongoose.model('Cliente',clienteSchema)