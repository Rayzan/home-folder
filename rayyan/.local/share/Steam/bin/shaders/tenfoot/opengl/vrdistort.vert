#version 120
//#extension GL_ARB_texture_rectangle : require
//#extension GL_ARB_texture_rectangle : enable

uniform mat4 g_MatTransform;
uniform float g_viewportWidth;
uniform float g_viewportHeight;
varying vec4 tex; 

void main()
{
	gl_Position =  g_MatTransform * gl_Vertex;
	gl_Position.x = ( gl_Position.x / ( g_viewportWidth/2.0 ) ) - 1;
	gl_Position.y = -(  gl_Position.y / ( g_viewportHeight/2.0 ) ) + 1;
	
	gl_Position.z = 0.0f;
	
	tex = gl_MultiTexCoord0;
}
