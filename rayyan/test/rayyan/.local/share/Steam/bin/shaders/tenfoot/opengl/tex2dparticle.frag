#version 120

uniform sampler2D Texture0;
uniform sampler2D Texture1;

uniform float particleSharpness;

varying vec4 tex; 
varying vec4 tex1; 
varying vec4 color; 


void main (void) 
{	
	vec4 texcol = color;
		
	vec2 uv = tex.st - 0.5;
	
	float radius = sqrt( dot( uv, uv ) );
	
	float flSharpRadius = ( clamp( particleSharpness, 0.0, 0.98 ) ) / 2.0; 
	float alpha = 1.0; 
	if ( radius < flSharpRadius )
	{
		alpha = 1.0;
	}
	else
	{
		alpha = clamp( (1.0 - ( (radius - flSharpRadius) / (0.5 - flSharpRadius ) ) ), 0.0, 1.0 );
	}
	
	gl_FragColor.r = color.r * color.a * alpha;
	gl_FragColor.g = color.g * color.a * alpha;
	gl_FragColor.b = color.b * color.a * alpha;
	gl_FragColor.a = color.a * alpha;
}
